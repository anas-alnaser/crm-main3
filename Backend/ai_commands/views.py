from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminRole
from activities.models import Activity
from clients.models import Client
from meetings.models import Meeting
from sales.models import Deal, Pipeline, Stage
from tasks.models import Task
from .models import AICommandLog
from .services import AICommandError, MissingAIKeyError, interpret_command


CONFIDENCE_THRESHOLD = 0.75

TIER_AUTO = AICommandLog.Tier.AUTO
TIER_CONFIRM = AICommandLog.Tier.CONFIRM
TIER_BLOCKED = AICommandLog.Tier.BLOCKED
TIER_UNKNOWN = AICommandLog.Tier.UNKNOWN

AUTO_INTENTS = {
    "create_meeting",
    "create_task",
    "log_activity",
    "move_deal",
    "create_deal",
    "create_company",
    "add_note",
    "schedule_followup",
}
CONFIRM_INTENTS = {
    "update_deal_value",
    "update_deal_close_date",
    "reassign_deal_owner",
    "edit_company_details",
    "edit_meeting",
    "update_task",
}
BLOCKED_INTENTS = {
    "delete_record",
    "delete_deal",
    "delete_company",
    "delete_task",
    "delete_meeting",
    "change_commission_rate",
    "change_user_role",
    "create_user",
    "deactivate_user",
    "bulk_operation",
}
SUPPORTED_INTENTS = AUTO_INTENTS | CONFIRM_INTENTS | BLOCKED_INTENTS


class AICommandSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


class AICommandConfirmSerializer(serializers.Serializer):
    draft = serializers.JSONField()
    text = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class AICommandUndoSerializer(serializers.Serializer):
    action_id = serializers.IntegerField(min_value=1)


def intent_tier(intent):
    if intent in AUTO_INTENTS:
        return TIER_AUTO
    if intent in CONFIRM_INTENTS:
        return TIER_CONFIRM
    if intent in BLOCKED_INTENTS:
        return TIER_BLOCKED
    return TIER_UNKNOWN


def sorted_missing(draft, missing):
    return sorted(set([*(draft.get("missing") or []), *missing]))


def pick_option(obj):
    label = str(obj)
    if isinstance(obj, Deal):
        label = f"{obj.title} - {obj.company.name}"
    elif isinstance(obj, Client):
        label = obj.name
    elif isinstance(obj, Task):
        label = obj.title
    elif isinstance(obj, Meeting):
        label = f"{obj.title} - {obj.start_datetime:%Y-%m-%d %H:%M}"
    elif hasattr(obj, "username"):
        label = obj.username
    return {"id": obj.id, "label": label}


def add_pick_list(options, label, queryset):
    if options is not None:
        options[label] = [pick_option(obj) for obj in queryset[:10]]


def resolve_one(queryset, label, missing, options=None):
    count = queryset.count()
    if count == 1:
        return queryset.first()
    if count == 0:
        missing.append(label)
        return None
    missing.append(f"{label}_ambiguous")
    add_pick_list(options, label, queryset)
    return None


def resolve_client(company_name, missing, required=True, options=None):
    if not company_name:
        if required:
            missing.append("company_name")
        return None
    exact = Client.objects.filter(name__iexact=company_name)
    if exact.count() == 1:
        return exact.first()
    contains = Client.objects.filter(name__icontains=company_name)
    return resolve_one(contains, "company_name", missing, options)


def resolve_deal(identifier, missing, required=True, options=None):
    if not identifier:
        if required:
            missing.append("deal_identifier")
        return None
    queryset = Deal.objects.select_related("company", "stage", "pipeline", "owner")
    exact_title = queryset.filter(title__iexact=identifier)
    if exact_title.count() == 1:
        return exact_title.first()
    title_matches = queryset.filter(title__icontains=identifier)
    if title_matches.count() == 1:
        return title_matches.first()
    if title_matches.count() > 1:
        missing.append("deal_identifier_ambiguous")
        add_pick_list(options, "deal_identifier", title_matches)
        return None
    company_matches = queryset.filter(Q(company__name__iexact=identifier) | Q(company__name__icontains=identifier))
    return resolve_one(company_matches, "deal_identifier", missing, options)


def resolve_stage(stage_name, deal, missing, required=True, options=None):
    if not stage_name:
        if required:
            missing.append("target_stage")
        return None
    if deal:
        scoped = Stage.objects.filter(pipeline=deal.pipeline)
        exact = scoped.filter(name__iexact=stage_name)
        if exact.count() == 1:
            return exact.first()
        contains = scoped.filter(name__icontains=stage_name)
        if contains.count() == 1:
            return contains.first()

    exact = Stage.objects.filter(name__iexact=stage_name)
    if exact.count() == 1:
        return exact.first()
    contains = Stage.objects.filter(name__icontains=stage_name)
    return resolve_one(contains, "target_stage", missing, options)


def resolve_task(identifier, missing, options=None):
    if not identifier:
        missing.append("task_identifier")
        return None
    exact = Task.objects.filter(title__iexact=identifier)
    if exact.count() == 1:
        return exact.first()
    return resolve_one(Task.objects.filter(title__icontains=identifier), "task_identifier", missing, options)


def resolve_meeting(identifier, missing, options=None):
    if not identifier:
        missing.append("meeting_identifier")
        return None
    exact = Meeting.objects.select_related("company", "deal", "owner").filter(title__iexact=identifier)
    if exact.count() == 1:
        return exact.first()
    return resolve_one(Meeting.objects.select_related("company", "deal", "owner").filter(title__icontains=identifier), "meeting_identifier", missing, options)


def resolve_user(username, missing, required=True, options=None):
    if not username:
        if required:
            missing.append("owner_username")
        return None
    User = get_user_model()
    exact = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username))
    if exact.count() == 1:
        return exact.first()
    contains = User.objects.filter(Q(username__icontains=username) | Q(first_name__icontains=username) | Q(last_name__icontains=username))
    return resolve_one(contains, "owner_username", missing, options)


def parse_decimal(value, label, missing):
    if value in (None, ""):
        missing.append(label)
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        missing.append(label)
        return None


def parse_date(value, label, missing, required=True):
    if not value:
        if required:
            missing.append(label)
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        missing.append(label)
        return None


def parse_meeting_datetimes(fields, missing):
    date_value = fields.get("date")
    start_time = fields.get("start_time")
    end_time = fields.get("end_time")
    if not date_value:
        missing.append("date")
    if not start_time:
        missing.append("start_time")
    if not date_value or not start_time:
        return None, None
    try:
        start = timezone.make_aware(datetime.fromisoformat(f"{date_value}T{start_time}"))
        end = timezone.make_aware(datetime.fromisoformat(f"{date_value}T{end_time}")) if end_time else start + timedelta(hours=1)
    except ValueError:
        missing.append("date_or_time")
        return None, None
    if end <= start:
        missing.append("end_time")
    return start, end


def response_base(draft, tier):
    return {
        "intent": draft.get("intent"),
        "tier": tier,
        "understood": {
            "intent": draft.get("intent"),
            "fields": draft.get("fields") or {},
            "confidence": draft.get("confidence", 0),
            "missing": draft.get("missing") or [],
        },
    }


def build_review_response(draft, missing, tier, reason, preview=None, options=None):
    merged_missing = sorted_missing(draft, missing)
    updated_draft = {**draft, "missing": merged_missing}
    return {
        **response_base(updated_draft, tier),
        "acted": False,
        "requires_confirmation": False,
        "requires_disambiguation": bool(options),
        "needs_review": not bool(options),
        "draft": updated_draft,
        "missing": merged_missing,
        "options": options or {},
        "reason": reason,
        "preview": preview or {},
    }


def build_confirmation_response(draft, missing, tier, reason, preview=None):
    return build_review_response(draft, missing, tier, reason, preview)


def build_blocked_response(draft, reason):
    return {
        **response_base(draft, TIER_BLOCKED),
        "acted": False,
        "blocked": True,
        "requires_confirmation": False,
        "refusal": reason,
        "summary": reason,
    }


def build_unknown_response(draft):
    return {
        **response_base(draft, TIER_UNKNOWN),
        "acted": False,
        "requires_confirmation": False,
        "blocked": True,
        "refusal": "That command is not supported by the CRM AI action framework.",
        "summary": "Unsupported AI command.",
    }


def model_key(instance):
    return instance._meta.label


def create_action(instance):
    return {"kind": "create", "model": model_key(instance), "object_id": instance.id}


def update_action(instance, changes):
    return {"kind": "update", "model": model_key(instance), "object_id": instance.id, "changes": changes}


def change_value(instance, field, new_value):
    old_value = getattr(instance, field)
    return {field: {"old": str(old_value) if old_value is not None else None, "new": str(new_value) if new_value is not None else None}}


def change_fk(instance, field, new_id):
    old_id = getattr(instance, f"{field}_id")
    return {f"{field}_id": {"old": old_id, "new": new_id}}


def apply_changes(instance, changes):
    update_fields = []
    for field_name, values in changes.items():
        model_field_name = field_name[:-3] if field_name.endswith("_id") else field_name
        model_field = instance._meta.get_field(model_field_name)
        old_value = values["old"]
        if field_name.endswith("_id"):
            setattr(instance, field_name, old_value)
        else:
            setattr(instance, field_name, None if old_value in ("", None) and model_field.null else model_field.to_python(old_value))
        update_fields.append(model_field_name)
    if hasattr(instance, "updated_at"):
        update_fields.append("updated_at")
    instance.save(update_fields=sorted(set(update_fields)))


class AICommandExecutor:
    def __init__(self, user):
        self.user = user

    def preview(self, draft):
        return self._dispatch(draft, execute=False)

    def execute(self, draft):
        return self._dispatch(draft, execute=True)

    def _dispatch(self, draft, execute):
        intent = draft.get("intent")
        method = getattr(self, f"handle_{intent}", None)
        if not method:
            return build_unknown_response(draft)
        return method(draft, execute)

    def success(self, draft, result, action_data=None, changes=None):
        return {
            **response_base(draft, intent_tier(draft.get("intent"))),
            "acted": True,
            "requires_confirmation": False,
            "requires_disambiguation": False,
            "undoable": bool(action_data),
            "action_data": action_data or {},
            "changes": changes or {},
            **result,
        }

    def handle_create_company(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        name = fields.get("company_name") or fields.get("name")
        if not name:
            missing.append("company_name")
        if name and Client.objects.filter(name__iexact=name).exists():
            missing.append("company_name_already_exists")
        if missing:
            return build_review_response(draft, missing, TIER_AUTO, "The company needs review before it can be created.", options=options)
        if not execute:
            return build_confirmation_response(draft, [], TIER_AUTO, "Ready to create company.")
        company = Client.objects.create(
            name=name,
            contact_person=fields.get("contact_person") or "",
            email=fields.get("email") or "",
            phone=fields.get("phone") or "",
            country=fields.get("country") or "",
            notes=fields.get("notes") or "",
        )
        return self.success(draft, {"company_id": company.id, "summary": f"Created company '{company.name}'."}, create_action(company))

    def handle_create_deal(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        title = fields.get("title") or fields.get("deal_identifier")
        if not title:
            missing.append("title")
        company = resolve_client(fields.get("company_name"), missing, options=options)
        stage = resolve_stage(fields.get("target_stage"), None, missing, options=options)
        owner = resolve_user(fields.get("owner_username"), missing, required=False, options=options) or self.user
        value = parse_decimal(fields.get("value"), "value", missing) if fields.get("value") not in (None, "") else None
        close_date = parse_date(fields.get("expected_close_date"), "expected_close_date", missing, required=False)
        if missing:
            return build_review_response(draft, missing, TIER_AUTO, "The deal needs review before it can be created.", options=options)
        if not execute:
            return build_confirmation_response(draft, [], TIER_AUTO, "Ready to create deal.")
        deal = Deal.objects.create(
            title=title,
            company=company,
            value=value,
            currency=fields.get("currency") or "JOD",
            pipeline=stage.pipeline,
            stage=stage,
            owner=owner,
            expected_close_date=close_date,
            notes=fields.get("notes") or "",
        )
        return self.success(draft, {"deal_id": deal.id, "summary": f"Created deal '{deal.title}' in {stage.name}."}, create_action(deal))

    def handle_move_deal(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        deal = resolve_deal(fields.get("deal_identifier"), missing, options=options)
        stage = resolve_stage(fields.get("target_stage"), deal, missing, options=options)
        if missing:
            return build_review_response(draft, missing, TIER_AUTO, "The deal move needs review before it can be applied.", options=options)
        if not execute:
            return build_confirmation_response(draft, [], TIER_AUTO, "Ready to move deal.")
        old_stage = deal.stage
        changes = {}
        changes.update(change_fk(deal, "pipeline", stage.pipeline_id))
        changes.update(change_fk(deal, "stage", stage.id))
        changes.update(change_value(deal, "status", Deal.Status.WON if stage.is_won else Deal.Status.LOST if stage.is_lost else Deal.Status.OPEN))
        deal.pipeline = stage.pipeline
        deal.stage = stage
        deal.save()
        return self.success(
            draft,
            {"deal_id": deal.id, "stage_id": stage.id, "summary": f"Moved deal '{deal.title}' from {old_stage.name} to {stage.name}."},
            update_action(deal, changes),
            {"stage": {"old": old_stage.name, "new": stage.name}},
        )

    def handle_create_meeting(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        title = fields.get("title") or ""
        if not title:
            missing.append("title")
        company = resolve_client(fields.get("company_name"), missing, options=options)
        deal = resolve_deal(fields.get("deal_identifier"), missing, required=False, options=options)
        start, end = parse_meeting_datetimes(fields, missing)
        if missing:
            return build_review_response(draft, missing, TIER_AUTO, "The meeting needs review before it can be scheduled.", options=options)
        if not execute:
            return build_confirmation_response(draft, [], TIER_AUTO, "Ready to schedule meeting.")
        meeting = Meeting.objects.create(
            title=title,
            description=fields.get("notes") or "",
            start_datetime=start,
            end_datetime=end,
            location=fields.get("location") or "",
            company=company,
            deal=deal,
            owner=self.user,
            status=Meeting.Status.SCHEDULED,
        )
        return self.success(draft, {"meeting_id": meeting.id, "summary": f"Created meeting '{meeting.title}' with {company.name} on {meeting.start_datetime:%Y-%m-%d at %H:%M}."}, create_action(meeting))

    def handle_create_task(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        title = fields.get("title") or ""
        if not title:
            missing.append("title")
        client = resolve_client(fields.get("company_name"), missing, required=False, options=options)
        deal = resolve_deal(fields.get("deal_identifier"), missing, required=False, options=options)
        due_date = parse_date(fields.get("due_date") or fields.get("date"), "due_date", missing, required=False)
        status_value = fields.get("status") or Task.Status.TODO
        if status_value not in Task.Status.values:
            missing.append("status")
        if missing:
            return build_review_response(draft, missing, TIER_AUTO, "The task needs review before it can be created.", options=options)
        if not execute:
            return build_confirmation_response(draft, [], TIER_AUTO, "Ready to create task.")
        task = Task.objects.create(title=title, description=fields.get("notes") or fields.get("content") or "", client=client, deal=deal, due_date=due_date, status=status_value)
        return self.success(draft, {"task_id": task.id, "summary": f"Created task '{task.title}'."}, create_action(task))

    def handle_log_activity(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        content = fields.get("content") or fields.get("notes") or ""
        if not content:
            missing.append("content")
        activity_type = fields.get("activity_type") or fields.get("type") or Activity.Type.NOTE
        if activity_type not in Activity.Type.values:
            missing.append("activity_type")
        client = resolve_client(fields.get("company_name"), missing, required=False, options=options)
        deal = resolve_deal(fields.get("deal_identifier"), missing, required=False, options=options)
        if missing:
            return build_review_response(draft, missing, TIER_AUTO, "The activity needs review before it can be logged.", options=options)
        if not execute:
            return build_confirmation_response(draft, [], TIER_AUTO, "Ready to log activity.")
        activity = Activity.objects.create(type=activity_type, content=content, client=client, deal=deal)
        return self.success(draft, {"activity_id": activity.id, "summary": f"Logged {activity.get_type_display().lower()} activity."}, create_action(activity))

    def handle_add_note(self, draft, execute):
        fields = {**(draft.get("fields") or {}), "activity_type": Activity.Type.NOTE}
        return self.handle_log_activity({**draft, "fields": fields}, execute)

    def handle_schedule_followup(self, draft, execute):
        fields = draft.get("fields") or {}
        followup_fields = {
            "title": fields.get("title") or f"Follow up{f' with {fields.get('company_name')}' if fields.get('company_name') else ''}",
            "company_name": fields.get("company_name"),
            "deal_identifier": fields.get("deal_identifier"),
            "due_date": fields.get("due_date") or fields.get("date"),
            "notes": fields.get("notes") or fields.get("content") or "",
        }
        return self.handle_create_task({**draft, "fields": followup_fields}, execute)

    def handle_update_deal_value(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        deal = resolve_deal(fields.get("deal_identifier"), missing, options=options)
        value = parse_decimal(fields.get("value"), "value", missing)
        if missing:
            return build_review_response(draft, missing, TIER_CONFIRM, "The deal value edit needs review before applying.", options=options)
        preview = {"record": deal.title, "field": "value", "old": str(deal.value or ""), "new": str(value)}
        if not execute:
            return build_confirmation_response(draft, [], TIER_CONFIRM, "Deal value edits always require confirmation.", preview)
        old = deal.value
        changes = change_value(deal, "value", value)
        deal.value = value
        deal.save(update_fields=["value", "updated_at"])
        return self.success(
            draft,
            {"deal_id": deal.id, "summary": f"Updated deal '{deal.title}' value from {old or 0} to {value}."},
            update_action(deal, changes),
            {"value": {"old": str(old or 0), "new": str(value)}},
        )

    def handle_update_deal_close_date(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        deal = resolve_deal(fields.get("deal_identifier"), missing, options=options)
        close_date = parse_date(fields.get("expected_close_date") or fields.get("date"), "expected_close_date", missing)
        if missing:
            return build_review_response(draft, missing, TIER_CONFIRM, "The close date edit needs review before applying.", options=options)
        preview = {"record": deal.title, "field": "expected_close_date", "old": str(deal.expected_close_date or ""), "new": str(close_date)}
        if not execute:
            return build_confirmation_response(draft, [], TIER_CONFIRM, "Deal close date edits always require confirmation.", preview)
        changes = change_value(deal, "expected_close_date", close_date)
        old = deal.expected_close_date
        deal.expected_close_date = close_date
        deal.save(update_fields=["expected_close_date", "updated_at"])
        return self.success(
            draft,
            {"deal_id": deal.id, "summary": f"Updated deal '{deal.title}' close date from {old or 'empty'} to {close_date}."},
            update_action(deal, changes),
            {"expected_close_date": {"old": str(old or ""), "new": str(close_date)}},
        )

    def handle_reassign_deal_owner(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        deal = resolve_deal(fields.get("deal_identifier"), missing, options=options)
        owner = resolve_user(fields.get("owner_username"), missing, options=options)
        if missing:
            return build_review_response(draft, missing, TIER_CONFIRM, "The owner change needs review before applying.", options=options)
        preview = {"record": deal.title, "field": "owner", "old": deal.owner.username, "new": owner.username}
        if not execute:
            return build_confirmation_response(draft, [], TIER_CONFIRM, "Deal owner changes always require confirmation.", preview)
        old_owner = deal.owner
        changes = change_fk(deal, "owner", owner.id)
        deal.owner = owner
        deal.save(update_fields=["owner", "updated_at"])
        return self.success(
            draft,
            {"deal_id": deal.id, "summary": f"Reassigned deal '{deal.title}' from {old_owner.username} to {owner.username}."},
            update_action(deal, changes),
            {"owner": {"old": old_owner.username, "new": owner.username}},
        )

    def handle_edit_company_details(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        company = resolve_client(fields.get("company_name"), missing, options=options)
        allowed = ["contact_person", "email", "phone", "country", "notes", "status"]
        changes = {field: fields[field] for field in allowed if field in fields and fields[field] not in (None, "")}
        if not changes:
            missing.append("company_details")
        if changes.get("status") and changes["status"] not in Client.Status.values:
            missing.append("status")
        if missing:
            return build_review_response(draft, missing, TIER_CONFIRM, "The company edit needs review before applying.", options=options)
        preview = {"record": company.name, "changes": {key: {"old": str(getattr(company, key) or ""), "new": str(value)} for key, value in changes.items()}}
        if not execute:
            return build_confirmation_response(draft, [], TIER_CONFIRM, "Company edits always require confirmation.", preview)
        old_new = {key: {"old": str(getattr(company, key) or ""), "new": str(value)} for key, value in changes.items()}
        action_changes = {}
        for key, value in changes.items():
            action_changes.update(change_value(company, key, value))
        for key, value in changes.items():
            setattr(company, key, value)
        company.save(update_fields=[*changes.keys(), "updated_at"])
        return self.success(draft, {"company_id": company.id, "summary": f"Updated company '{company.name}'."}, update_action(company, action_changes), old_new)

    def handle_edit_meeting(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        meeting = resolve_meeting(fields.get("meeting_identifier") or fields.get("title"), missing, options=options)
        changes = {}
        if fields.get("status"):
            if fields["status"] not in Meeting.Status.values:
                missing.append("status")
            else:
                changes["status"] = fields["status"]
        for field in ["title", "location", "notes"]:
            if field in fields and fields[field] not in (None, ""):
                changes["description" if field == "notes" else field] = fields[field]
        if fields.get("date") or fields.get("start_time") or fields.get("end_time"):
            start, end = parse_meeting_datetimes(fields, missing)
            changes["start_datetime"] = start
            changes["end_datetime"] = end
        if not changes:
            missing.append("meeting_details")
        if missing:
            return build_review_response(draft, missing, TIER_CONFIRM, "The meeting edit needs review before applying.", options=options)
        preview = {"record": meeting.title, "changes": {key: {"old": str(getattr(meeting, key) or ""), "new": str(value)} for key, value in changes.items()}}
        if not execute:
            return build_confirmation_response(draft, [], TIER_CONFIRM, "Meeting edits always require confirmation.", preview)
        old_new = {key: {"old": str(getattr(meeting, key) or ""), "new": str(value)} for key, value in changes.items()}
        action_changes = {}
        for key, value in changes.items():
            action_changes.update(change_value(meeting, key, value))
        for key, value in changes.items():
            setattr(meeting, key, value)
        meeting.save(update_fields=[*changes.keys(), "updated_at"])
        return self.success(draft, {"meeting_id": meeting.id, "summary": f"Updated meeting '{meeting.title}'."}, update_action(meeting, action_changes), old_new)

    def handle_update_task(self, draft, execute):
        fields = draft.get("fields") or {}
        missing = []
        options = {}
        task = resolve_task(fields.get("task_identifier") or fields.get("title"), missing, options=options)
        changes = {}
        for field in ["title", "description"]:
            if field in fields and fields[field] not in (None, ""):
                changes[field] = fields[field]
        if fields.get("status"):
            if fields["status"] not in Task.Status.values:
                missing.append("status")
            else:
                changes["status"] = fields["status"]
        if fields.get("due_date") or fields.get("date"):
            changes["due_date"] = parse_date(fields.get("due_date") or fields.get("date"), "due_date", missing)
        if not changes:
            missing.append("task_details")
        if missing:
            return build_review_response(draft, missing, TIER_CONFIRM, "The task edit needs review before applying.", options=options)
        preview = {"record": task.title, "changes": {key: {"old": str(getattr(task, key) or ""), "new": str(value)} for key, value in changes.items()}}
        if not execute:
            return build_confirmation_response(draft, [], TIER_CONFIRM, "Task edits always require confirmation.", preview)
        old_new = {key: {"old": str(getattr(task, key) or ""), "new": str(value)} for key, value in changes.items()}
        action_changes = {}
        for key, value in changes.items():
            action_changes.update(change_value(task, key, value))
        for key, value in changes.items():
            setattr(task, key, value)
        task.save(update_fields=[*changes.keys(), "updated_at"])
        return self.success(draft, {"task_id": task.id, "summary": f"Updated task '{task.title}'."}, update_action(task, action_changes), old_new)


class AICommandView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = AICommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_text = serializer.validated_data["text"]
        log_data = {"user": request.user, "raw_text": raw_text, "outcome": AICommandLog.Outcome.ERROR}

        try:
            draft = interpret_command(raw_text, request.user)
        except MissingAIKeyError as exc:
            log_data["summary"] = str(exc)
            AICommandLog.objects.create(**log_data)
            return Response({"detail": "AI command service is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except (AICommandError, ValueError) as exc:
            log_data["summary"] = str(exc)
            AICommandLog.objects.create(**log_data)
            return Response({"detail": "Could not interpret command.", "error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        response_payload = self.evaluate_draft(draft, request.user)
        log = self.write_log(log_data, draft, response_payload)
        if response_payload.get("acted"):
            response_payload["action_id"] = log.id
        return Response(response_payload)

    def evaluate_draft(self, draft, user):
        intent = draft.get("intent")
        tier = intent_tier(intent)
        if tier == TIER_UNKNOWN:
            return build_unknown_response(draft)
        if tier == TIER_BLOCKED:
            return build_blocked_response(draft, "This action is blocked for safety. Please do it manually in the CRM/admin screen.")

        if draft.get("confidence", 0) < CONFIDENCE_THRESHOLD:
            return build_review_response(draft, ["confidence"], tier, "Low confidence command. I need a more specific instruction before acting.")
        return AICommandExecutor(user).execute(draft)

    def write_log(self, log_data, draft, response_payload):
        log_data["resolved_intent"] = draft.get("intent") or ""
        log_data["tier"] = response_payload.get("tier", TIER_UNKNOWN)
        log_data["draft"] = response_payload.get("draft", draft)
        log_data["action_data"] = response_payload.get("action_data") or {}
        log_data["summary"] = response_payload.get("summary") or response_payload.get("reason") or response_payload.get("refusal") or ""
        if response_payload.get("acted"):
            log_data["outcome"] = AICommandLog.Outcome.EXECUTED
        elif response_payload.get("blocked"):
            log_data["outcome"] = AICommandLog.Outcome.BLOCKED
        elif response_payload.get("requires_disambiguation") or response_payload.get("needs_review"):
            log_data["outcome"] = AICommandLog.Outcome.DRAFT_RETURNED
        else:
            log_data["outcome"] = AICommandLog.Outcome.ERROR
        return AICommandLog.objects.create(**log_data)


class AICommandConfirmView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        return Response(
            {"detail": "AI command confirmation is no longer used. Confident resolved commands execute immediately; ambiguous commands must be clarified."},
            status=status.HTTP_410_GONE,
        )


class AICommandUndoView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = AICommandUndoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action_id = serializer.validated_data["action_id"]
        try:
            log = AICommandLog.objects.get(id=action_id, user=request.user)
        except AICommandLog.DoesNotExist:
            return Response({"detail": "AI action was not found."}, status=status.HTTP_404_NOT_FOUND)

        if log.undone_at:
            return Response({"detail": "This AI action has already been undone."}, status=status.HTTP_400_BAD_REQUEST)
        action_data = log.action_data or {}
        if not action_data:
            return Response({"detail": "This AI action cannot be undone."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = self.undo_action(action_data)
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        log.undone_at = timezone.now()
        log.outcome = AICommandLog.Outcome.UNDONE
        log.summary = f"Undone: {log.summary}"
        log.save(update_fields=["undone_at", "outcome", "summary"])
        return Response({"undone": True, "action_id": log.id, "summary": result})

    def undo_action(self, action_data):
        model_label = action_data.get("model")
        object_id = action_data.get("object_id")
        kind = action_data.get("kind")
        if not model_label or not object_id or kind not in {"create", "update"}:
            raise LookupError("This AI action cannot be undone.")
        app_label, model_name = model_label.split(".", 1)
        model = apps.get_model(app_label, model_name)

        if kind == "create":
            try:
                obj = model.objects.get(id=object_id)
            except model.DoesNotExist as exc:
                raise LookupError("The created record no longer exists.") from exc
            label = str(obj)
            obj.delete()
            return f"Deleted created record '{label}'."

        try:
            obj = model.objects.get(id=object_id)
        except model.DoesNotExist as exc:
            raise LookupError("The edited record no longer exists.") from exc
        apply_changes(obj, action_data.get("changes") or {})
        return f"Restored '{obj}' to its previous values."
