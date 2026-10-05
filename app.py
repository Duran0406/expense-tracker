import os
import time
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from auth import authenticate, register_user
from database import (CATEGORIES, PAYMENT_METHODS, add_expense, delete_expense,
                      get_expenses, get_user, init_db, validate_expense)

st.set_page_config(page_title='Harcama Takip', page_icon='💰', layout='wide')
# Root-level Streamlit secrets also become environment variables for the storage layer.
try:
    cloud_database_url = st.secrets.get('DATABASE_URL', '')
except FileNotFoundError:
    cloud_database_url = ''
if cloud_database_url:
    os.environ['DATABASE_URL'] = cloud_database_url


@st.cache_resource
def initialize_storage():
    init_db()


initialize_storage()


def money(cents):
    return f'{cents / 100:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.') + ' ₺'


def start_session(user=None, demo=False):
    st.session_state.clear()
    st.session_state['account'] = user
    st.session_state['demo'] = demo
    st.session_state['signed_in_at'] = time.time()
    if demo:
        today = date.today()
        st.session_state['demo_expenses'] = [
            dict(id=i, amount_cents=cents, category=cat, payment_method=pay,
                 description=desc, expense_date=(today - timedelta(days=days)).isoformat())
            for i, (cents, cat, pay, desc, days) in enumerate([
                (18500, CATEGORIES[0], PAYMENT_METHODS[0], 'Öğle yemeği', 0),
                (62000, CATEGORIES[1], PAYMENT_METHODS[0], 'Haftalık market', 0),
                (6500, CATEGORIES[2], PAYMENT_METHODS[1], 'Ulaşım', 0),
                (24000, CATEGORIES[5], PAYMENT_METHODS[2], 'Sinema', 0),
                (35000, CATEGORIES[6], PAYMENT_METHODS[2], 'Kitaplar', 2),
                (12500, CATEGORIES[0], PAYMENT_METHODS[1], 'Kahvaltı', 5),
            ], start=1)
        ]


st.title('💰 Kişisel Harcama Takip')
st.caption('Harcamalarını kaydet, dağılımını gör, bütçeni takip et.')

if st.session_state.get('signed_in_at') and time.time() - st.session_state['signed_in_at'] >= 8 * 60 * 60:
    st.session_state.clear()
    st.info('Oturum süren doldu. Lütfen yeniden giriş yap.')

if not st.session_state.get('account') and not st.session_state.get('demo'):
    st.subheader('Hesabına hoş geldin')
    st.write('Her hesap yalnızca kendi harcamalarını görür. Başlamak için giriş yap veya hesap oluştur.')
    login_tab, register_tab = st.tabs(['Giriş yap', 'Kayıt ol'])
    with login_tab:
        with st.form('login'):
            username = st.text_input('Kullanıcı adı', max_chars=30, key='login_username')
            password = st.text_input('Şifre', type='password', max_chars=128, key='login_password')
            login = st.form_submit_button('Giriş yap', width='stretch', type='primary')
        if login:
            try:
                user = authenticate(username, password)
                if user:
                    start_session(user)
                    st.rerun()
                st.error('Kullanıcı adı veya şifre hatalı.')
            except ValueError as exc:
                st.error(str(exc))
    with register_tab:
        with st.form('register'):
            new_username = st.text_input('Kullanıcı adı', max_chars=30, key='register_username',
                                         help='3–30 karakter: a-z, 0-9 ve alt çizgi.')
            new_password = st.text_input('Şifre', type='password', max_chars=128, key='register_password',
                                         help='En az 15 karakter. Hatırlayabileceğin uzun bir cümle seç.')
            confirmation = st.text_input('Şifreyi tekrar gir', type='password', max_chars=128)
            register = st.form_submit_button('Hesap oluştur', width='stretch', type='primary')
        if register:
            if new_password != confirmation:
                st.error('Şifreler eşleşmiyor.')
            else:
                try:
                    start_session(register_user(new_username, new_password))
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    st.divider()
    st.write('Önce denemek ister misin? Örnek verilerle uygulamayı keşfet.')
    if st.button('✨ Demo hesabını dene', width='stretch'):
        start_session(demo=True)
        st.rerun()
    st.caption('Demo değişiklikleri yalnızca bu oturumda kalır. Şifre sıfırlama henüz desteklenmiyor.')
    st.stop()

demo = st.session_state.get('demo', False)
account = st.session_state.get('account')
if not demo and not get_user(account['id']):
    st.session_state.clear()
    st.rerun()

with st.sidebar:
    st.subheader('👤 Demo hesabı' if demo else f"👤 {account['username']}")
    if st.button('Çıkış yap', width='stretch'):
        st.session_state.clear()
        st.rerun()
    st.divider()
    st.header('➕ Yeni Harcama Ekle')
    with st.form('expense_form', clear_on_submit=True):
        amount = st.number_input('Tutar (₺)', min_value=0.01, max_value=1_000_000_000.0,
                                 step=0.50, format='%.2f')
        category = st.selectbox('Kategori', CATEGORIES)
        payment_method = st.selectbox('Ödeme Yöntemi', PAYMENT_METHODS)
        description = st.text_input('Açıklama', max_chars=500, placeholder='Örn: Öğle yemeği')
        expense_date = st.date_input('Tarih', value=date.today(), max_value=date.today())
        submitted = st.form_submit_button('💾 Kaydet', width='stretch', type='primary')
    if submitted:
        try:
            if demo:
                cents = validate_expense(amount, category, payment_method, description, expense_date)
                rows = st.session_state['demo_expenses']
                rows.insert(0, dict(id=max((r['id'] for r in rows), default=0) + 1,
                                    amount_cents=cents, category=category, payment_method=payment_method,
                                    description=description.strip(), expense_date=expense_date.isoformat()))
            else:
                add_expense(account['id'], amount, category, payment_method, description, expense_date)
            st.session_state['flash'] = 'Harcama kaydedildi.'
            st.session_state['pending_period'] = (expense_date, expense_date)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

if demo:
    st.info('Demo hesabındasın. Veriler örnektir; yaptığın değişiklikler bu oturumdan çıkınca sıfırlanır.')
if message := st.session_state.pop('flash', None):
    st.success(message)
if pending := st.session_state.pop('pending_period', None):
    st.session_state['period_default'] = pending
    st.session_state['period_version'] = st.session_state.get('period_version', 0) + 1
    st.session_state['category_filter'] = 'Tüm kategoriler'

filter_col1, filter_col2 = st.columns([2, 1])
with filter_col1:
    period = st.date_input('📅 Tarih aralığı',
                           value=st.session_state.get('period_default', (date.today().replace(day=1), date.today())),
                           max_value=date.today(), key=f"period_{st.session_state.get('period_version', 0)}",
                           format='DD/MM/YYYY')
with filter_col2:
    selected_category = st.selectbox('📂 Kategori filtresi', ['Tüm kategoriler'] + CATEGORIES,
                                     key='category_filter')
if len(period) != 2:
    st.info('Lütfen tarih aralığının bitişini de seç.')
    st.stop()
start_date, end_date = period
category_filter = None if selected_category == 'Tüm kategoriler' else selected_category
if demo:
    expenses = sorted([row for row in st.session_state['demo_expenses']
                       if start_date.isoformat() <= row['expense_date'] <= end_date.isoformat()
                       and (not category_filter or row['category'] == category_filter)],
                      key=lambda row: (row['expense_date'], row['id']), reverse=True)
else:
    expenses = get_expenses(account['id'], start_date, end_date, category_filter)

st.caption('Toplamlar ve grafikler seçili tarih aralığına ve kategoriye göre hesaplanır.')
totals = {method: sum(row['amount_cents'] for row in expenses if row['payment_method'] == method)
          for method in PAYMENT_METHODS}
cards = st.columns(4)
cards[0].metric('📊 Seçili dönem toplamı', money(sum(row['amount_cents'] for row in expenses)))
for column, method in zip(cards[1:], PAYMENT_METHODS):
    column.metric(method, money(totals[method]))
st.divider()

if expenses:
    df = pd.DataFrame(expenses)
    left, right = st.columns(2)
    for column, field, title, colors in [
        (left, 'category', '📂 Kategoriye Göre Dağılım', px.colors.qualitative.Set3),
        (right, 'payment_method', '💳 Ödeme Yöntemine Göre Dağılım', ['#FF6B6B', '#4ECDC4', '#45B7D1']),
    ]:
        with column:
            st.subheader(title)
            summary = df.groupby(field, as_index=False)['amount_cents'].sum()
            summary['total'] = summary['amount_cents'] / 100
            labels = CATEGORIES if field == 'category' else PAYMENT_METHODS
            color_map = {label: colors[i % len(colors)] for i, label in enumerate(labels)}
            figure = px.pie(summary, values='total', names=field, color=field,
                            color_discrete_map=color_map, hole=0)
            figure.update_traces(textposition='inside', textinfo='percent', texttemplate='%{percent:.1%}',
                                 hovertemplate='%{label}<br>%{value:.2f} ₺<br>%{percent:.1%}<extra></extra>')
            figure.update_layout(legend=dict(orientation='h', yanchor='top', y=-0.1,
                                              xanchor='center', x=0.5),
                                 margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(figure, width='stretch')
    st.divider()

st.subheader(f'📋 Harcamalar · {len(expenses)} kayıt')
if not expenses:
    st.info('Bu filtrelere uygun harcama yok. Sol panelden harcama ekleyebilir veya filtreleri değiştirebilirsin.')
for expense in expenses:
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 1])
        with c1:
            st.text(expense['description'] or 'Açıklama yok')
            st.caption(date.fromisoformat(expense['expense_date']).strftime('%d/%m/%Y'))
        c2.write(expense['category'])
        c3.write(expense['payment_method'])
        c4.write(money(expense['amount_cents']))
        with c5:
            if st.button('🗑️', key=f"delete_{expense['id']}", help='Bu harcamayı sil'):
                st.session_state['confirm_delete'] = expense['id']
        if st.session_state.get('confirm_delete') == expense['id']:
            st.warning('Bu harcama silinsin mi?')
            yes, no = st.columns(2)
            if yes.button('Evet, sil', key=f"confirm_{expense['id']}"):
                if demo:
                    st.session_state['demo_expenses'] = [r for r in st.session_state['demo_expenses']
                                                         if r['id'] != expense['id']]
                else:
                    delete_expense(account['id'], expense['id'])
                st.session_state.pop('confirm_delete', None)
                st.session_state['flash'] = 'Harcama silindi.'
                st.rerun()
            if no.button('Vazgeç', key=f"cancel_{expense['id']}"):
                st.session_state.pop('confirm_delete', None)
                st.rerun()

st.divider()
st.caption('Harcama Takip · Python, Streamlit, SQLite & Plotly')
