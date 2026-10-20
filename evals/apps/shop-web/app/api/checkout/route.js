import { back, currentUser } from '../../../lib/session';
import { checkout, shop } from '../../../lib/store';

export async function POST(request) {
  const user = await currentUser();
  if (!user) {
    return back('/login');
  }
  const form = await request.formData();
  const result = checkout(shop(), user, String(form.get('card') ?? ''));
  return back(result.error ? `/checkout?error=${result.error}` : '/orders');
}
