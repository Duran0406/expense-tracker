"""Run locally to create/verify the owner's account and attach legacy records."""
import argparse
import getpass

from auth import authenticate, normalize_username, register_user
from database import claim_legacy_expenses, connection, init_db


def main():
    parser = argparse.ArgumentParser(description='Eski harcamaları kendi hesabınıza bağlayın.')
    parser.add_argument('--username', default='Duran')
    args = parser.parse_args()
    init_db()
    username = normalize_username(args.username)
    with connection() as conn:
        exists = conn.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone()
    if exists:
        user = authenticate(username, getpass.getpass('Hesabınızın şifresi: '))
        if not user:
            raise ValueError('Şifre hatalı. Hiçbir harcama aktarılmadı.')
    else:
        password = getpass.getpass('Yeni şifreniz (en az 15 karakter): ')
        if password != getpass.getpass('Şifreyi tekrar girin: '):
            raise ValueError('Şifreler eşleşmiyor. Hiçbir harcama aktarılmadı.')
        user = register_user(username, password)
    count = claim_legacy_expenses(user['id'])
    print(f'{count} eski harcama {username} hesabına bağlandı.')


if __name__ == '__main__':
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
