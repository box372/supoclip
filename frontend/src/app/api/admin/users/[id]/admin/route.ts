import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { getServerSession } from "@/server/session";

async function requireAdmin() {
  const session = await getServerSession();
  if (!session?.user?.id) {
    return { error: NextResponse.json({ error: "Unauthorized" }, { status: 401 }) };
  }

  const isAdmin = Boolean((session.user as { is_admin?: boolean }).is_admin);

  if (!isAdmin) {
    return { error: NextResponse.json({ error: "Forbidden" }, { status: 403 }) };
  }

  return { session };
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const adminCheck = await requireAdmin();
    if (adminCheck.error) {
      return adminCheck.error;
    }

    const { id } = await params;
    const body = await request.json();
    const { is_admin } = body as { is_admin?: unknown };

    if (typeof is_admin !== "boolean") {
      return NextResponse.json({ error: "is_admin must be a boolean" }, { status: 400 });
    }

    const updated = await prisma.user.update({
      where: { id },
      data: { is_admin },
      select: {
        id: true,
        email: true,
        is_admin: true,
      },
    });

    return NextResponse.json({ user: updated });
  } catch (error) {
    console.error("Failed to update admin flag:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
