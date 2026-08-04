"use client";

import { ProfileForm } from "@/components/ProfileForm";
import { StaticDemoNotice } from "@/components/StaticDemoNotice";
import { IS_STATIC_DEMO } from "@/lib/deployment";

export default function ProfilePage() {
  return (
    <main className="wrap">{IS_STATIC_DEMO ? <StaticDemoNotice /> : <ProfileForm />}</main>
  );
}
