import io
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

LOGIN_URL = 'http://webpage.boledragon.com:8080/accounts/login/'
QUERY_URL = 'http://webpage.boledragon.com:8080/forever_new/query/'

# pull your credentials from Streamlit secrets
USER = st.secrets["credentials"]["username"]
PASS = st.secrets["credentials"]["password"]

def fetch_user(session, uid):
    # 1) refresh CSRF on query page
    qpg = session.get(QUERY_URL)
    soup_q = BeautifulSoup(qpg.text, 'html.parser')
    csrf_q = soup_q.find('input', {'name':'csrfmiddlewaretoken'})['value']

    # 2) post the user_id
    resp = session.post(
        QUERY_URL,
        data={'csrfmiddlewaretoken': csrf_q, 'user_id': uid},
        headers={'Referer': QUERY_URL}
    )
    soup = BeautifulSoup(resp.text, 'html.parser')
    tbl = soup.find('p', string=lambda t: 'User properties' in t)\
              .find_next_sibling('table')
    rows = tbl.find_all('tr')

    out = {'queried_user_id': uid}
    # first header/data
    if len(rows) >= 2:
        keys = [th.get_text(strip=True) for th in rows[0].find_all('th')]
        vals = [td.get_text(strip=True) for td in rows[1].find_all('td')]
        out.update(zip(keys, vals))
    # second header/data
    if len(rows) >= 4:
        keys2 = [th.get_text(strip=True) for th in rows[2].find_all('th')]
        vals2 = [td.get_text(strip=True) for td in rows[3].find_all('td')]
        out.update(zip(keys2, vals2))

    return out

st.title("Bulk User-ID Detail Fetcher")
uploaded = st.file_uploader("Upload your input_ids.xlsx", type="xlsx")

if uploaded:
    # read input IDs
    df_ids = pd.read_excel(uploaded, dtype=str)
    user_ids = df_ids.iloc[:,0].tolist()

    # login once
    session = requests.Session()
    lp = session.get(LOGIN_URL)
    soup_l = BeautifulSoup(lp.text, 'html.parser')
    csrf_l = soup_l.find('input', {'name':'csrfmiddlewaretoken'})['value']
    session.post(
        LOGIN_URL,
        data={'csrfmiddlewaretoken': csrf_l, 'username': USER, 'password': PASS},
        headers={'Referer': LOGIN_URL}
    )

    # parallel fetch all users
    with ThreadPoolExecutor(10) as exe:
        futures = [exe.submit(fetch_user, session, uid) for uid in user_ids]
        results = [f.result() for f in as_completed(futures)]

    out_df = pd.DataFrame(results)

    # ─── in-memory Excel ────────────────────────────────────────────────────────
    buffer = io.BytesIO()
    out_df.to_excel(buffer, index=False, engine='openpyxl')
    buffer.seek(0)

    st.download_button(
        label="Download results.xlsx",
        data=buffer.getvalue(),
        file_name="results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
