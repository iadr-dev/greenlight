import { COOKIE, back } from '../../../lib/session';
import { login } from '../../../lib/store';

export async function POST(request) {
  const form = await request.formData();
  const name = String(form.get('name') ?? '');
  if (!login(name, String(form.get('password') ?? ''))) {
    return back('/login?error=credentials');
  }
  const response = back('/cart');
  response.headers.append('Set-Cookie', `${COOKIE}=${encodeURIComponent(name)}; Path=/; HttpOnly; SameSite=Lax`);
  return response;
}
