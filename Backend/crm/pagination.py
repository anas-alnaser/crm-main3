from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Standard page-number pagination with a client-controllable, capped size.

    Response shape:
        {"count", "next", "previous", "page", "page_size", "total_pages", "results"}
    """

    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        from rest_framework.response import Response

        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "total_pages": self.page.paginator.num_pages,
                "results": data,
            }
        )
