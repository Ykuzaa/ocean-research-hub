"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { ApiError } from "@/app/lib/api";
import { submitVerdict } from "@/app/lib/corpusV2";

const AUDITOR_COOKIE = "ocean-auditeur";

export async function getAuditor(): Promise<string> {
  return (await cookies()).get(AUDITOR_COOKIE)?.value ?? "";
}

/**
 * Records one verdict and moves to the next claim.
 *
 * The browser never calls the API directly: the verdict is signed with the auditor
 * stored in this session's cookie and posted from the server.
 */
export async function recordVerdict(formData: FormData) {
  const claimId = String(formData.get("claim_id") ?? "");
  const decision = String(formData.get("decision") ?? "");
  const note = String(formData.get("note") ?? "").trim();
  const auditor = String(formData.get("auditor") ?? "").trim();
  const slug = String(formData.get("slug") ?? "");
  const back = (query: Record<string, string>) => {
    const params = new URLSearchParams(query);
    if (slug) params.set("slug", slug);
    const encoded = params.toString();
    redirect(encoded ? `/revue?${encoded}` : "/revue");
  };

  if (!auditor) back({ error: "Signe ton audit : mets ton nom avant de décider." });
  (await cookies()).set(AUDITOR_COOKIE, auditor, { httpOnly: true, sameSite: "lax", maxAge: 60 * 60 * 24 * 365 });

  try {
    await submitVerdict({ claim_id: claimId, decision, auditor, note: note || null });
  } catch (error) {
    back({ error: error instanceof ApiError ? error.message : "enregistrement impossible" });
  }

  revalidatePath("/revue");
  back({ done: decision });
}
