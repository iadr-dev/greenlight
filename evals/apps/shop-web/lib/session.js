// A sign-in is a cookie holding the user's name. Enough for an evaluation app; not for a real shop.
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

export const COOKIE = 'shop_session';

export async function currentUser() {
  const jar = await cookies();
  return jar.get(COOKIE)?.value ?? null;
}

// Pages that need a signed-in user send everyone else to the sign-in page.
export async function requireUser() {
  const user = await currentUser();
  if (!user) {
    redirect('/login');
  }
  return user;
}

// A relative address, so the browser stays on the host it came from (and keeps its cookie).
export function back(path) {
  return new Response(null, { status: 303, headers: { Location: path } });
}
