import { zodResolver } from "@hookform/resolvers/zod";
import { LockKeyhole } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { MotionDiv } from "../components/ui/motion";
import { useAuth } from "../lib/auth";

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const form = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });

  if (user) {
    return <Navigate to="/" replace />;
  }

  const onSubmit = form.handleSubmit(async (values) => {
    setError("");
    try {
      await login(values.username.trim(), values.password.trim());
      navigate("/");
    } catch {
      setError("Invalid username or password.");
    }
  });

  return (
    <div className="grid min-h-screen place-items-center bg-background px-6">
      <MotionDiv className="w-full max-w-md" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, ease: "easeOut" }}>
      <form onSubmit={onSubmit} className="surface-card p-7">
        <div className="mb-7 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm shadow-primary/25">
            <LockKeyhole className="h-5 w-5" />
          </div>
          <div>
            <p className="page-kicker">Fueldezign</p>
            <h1 className="text-2xl font-semibold leading-tight">Private CRM</h1>
            <p className="text-sm text-muted-foreground">Agency sales and delivery workspace</p>
          </div>
        </div>
        <label className="field-label mb-4">
          Username
          <Input className="mt-2" autoComplete="username" placeholder="fueldezign" {...form.register("username")} />
          {form.formState.errors.username && <p className="field-hint text-primary">{form.formState.errors.username.message}</p>}
        </label>
        <label className="field-label mb-4">
          Password
          <Input className="mt-2" type="password" autoComplete="current-password" placeholder="Your password" {...form.register("password")} />
          {form.formState.errors.password && <p className="field-hint text-primary">{form.formState.errors.password.message}</p>}
        </label>
        {error && <p className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-500">{error}</p>}
        <Button className="w-full" disabled={form.formState.isSubmitting}>
          Login
        </Button>
      </form>
      </MotionDiv>
    </div>
  );
}
