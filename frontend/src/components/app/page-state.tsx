"use client";

import Image from "next/image";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function PageLoading() {
  const t = useTranslations("library");
  return <div role="status" aria-label={t("loading")} className="mx-auto max-w-5xl space-y-5 px-4 py-8">
    <span className="sr-only">{t("loadingEllipsis")}</span>
    <div className="flex items-center gap-2 pb-2">
      <Image src="/logo.png" alt="" width={22} height={22} className="size-[22px] rounded-md" priority />
      <span className="font-display text-sm font-semibold tracking-tight">ChunkVex AI</span>
      <span className="ml-1 size-1.5 animate-pulse rounded-full bg-brand" aria-hidden />
    </div>
    <Skeleton className="h-9 w-48" />
    {[0, 1, 2].map((key) => <Skeleton key={key} className="h-32 w-full rounded-xl" />)}
  </div>;
}

export function PageError({ message, retry }: { message: string; retry?: () => void }) {
  const t = useTranslations("library");
  return <div role="alert" className="mx-auto max-w-xl space-y-4 px-4 py-12 text-center">
    <h1 className="text-2xl font-semibold">{t("somethingWrong")}</h1>
    <p className="text-muted-foreground">{message}</p>
    {retry && <Button variant="outline" onClick={retry}>{t("tryAgain")}</Button>}
  </div>;
}
