import { Navigate, Route, Routes } from "react-router-dom";

import { AdminRoute } from "./components/AdminRoute";
import { DashboardLayout } from "./components/DashboardLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { ActivitiesPage } from "./pages/ActivitiesPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { BrandProfilesPage } from "./pages/BrandProfilesPage";
import { ClientsPage } from "./pages/ClientsPage";
import { DealsPage } from "./pages/DealsPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { LeadsPage } from "./pages/LeadsPage";
import { LoginPage } from "./pages/LoginPage";
import { MyShiftPage } from "./pages/MyShiftPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PipelinePage } from "./pages/PipelinePage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { SchedulePage } from "./pages/SchedulePage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";
import { UsersPage } from "./pages/UsersPage";
import { WorkforcePage } from "./pages/WorkforcePage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<PipelinePage />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/deals" element={<DealsPage />} />
          <Route path="/clients" element={<ClientsPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/activities" element={<ActivitiesPage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/my-shift" element={<MyShiftPage />} />
          <Route path="/leads" element={<LeadsPage />} />
          <Route element={<AdminRoute />}>
            <Route path="/users" element={<UsersPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/workforce" element={<WorkforcePage />} />
            <Route path="/audit" element={<AuditLogPage />} />
            <Route path="/brands" element={<BrandProfilesPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
