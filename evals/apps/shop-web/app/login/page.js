import { MESSAGES } from '../../lib/store';

export const dynamic = 'force-dynamic';

export default async function Login({ searchParams }) {
  const { error } = await searchParams;
  return (
    <main>
      <h1>Sign in</h1>
      {error && MESSAGES[error] ? (
        <p role="alert" data-testid="login-error">
          {MESSAGES[error]}
        </p>
      ) : null}
      <form method="post" action="/api/login">
        <label>
          Name <input name="name" />
        </label>
        <label>
          Password <input name="password" type="password" />
        </label>
        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}
