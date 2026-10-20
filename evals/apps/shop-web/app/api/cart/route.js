import { back, currentUser } from '../../../lib/session';
import { addToCart, shop } from '../../../lib/store';

export async function POST(request) {
  const user = await currentUser();
  if (!user) {
    return back('/login');
  }
  const form = await request.formData();
  addToCart(shop(), user, String(form.get('sku') ?? ''));
  return back('/cart');
}
