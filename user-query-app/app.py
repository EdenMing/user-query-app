import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

LOGIN_URL = 'http://webpage.boledragon.com:8080/accounts/login/'
QUERY_URL = 'http://webpage.boledragon.com:8080/forever_new/query/'

# Pull credentials from Streamlit “Secrets” (keeps them out of your code repo)
USERNAME = st.secrets["credentials"]["username"]
PASSWORD = st.secrets["credentials"]["password"]

def fetch_user(session, uid):
    # 1) GET query page to refresh CSRF
    qpg = session.get(QUERY_URL)
    soup_q = BeautifulSoup(qpg.text, 'html.parser')
    csrf_q = soup_q.find('input', {'name':'csrfmiddlewaretoken'})['value']

    # 2) POST the user_id
    resp = session.post(
        QUERY_URL,
        data={'csrfmiddlewaretoken': csrf_q, 'user_id': uid},
        headers={'Referer': QUERY_URL}
    )
    soup = BeautifulSoup(resp.text, 'html.parser')
    tbl = soup.find('p', string=lambda t: 'User properties' in t) \
              .find_next_sibling('table')
    rows = tbl.find_all('tr')
    out = {'queried_user_id': uid}

    # First header/data
    if len(rows) >= 2:
        keys  = [th.get_text(strip=True) for th in rows[0].find_all('th')]
        vals  = [td.get_text(strip=True) for td in rows[1].find_all('td')]
        out.update(zip(keys, vals))
    # Second header/data
    if len(rows) >= 4:
        keys2 = [th.get_text(strip=True) for th in rows[2].find_all('th')]
        vals2 = [td.get_text(strip=True) for td in rows[3].find_all('td')]
        out.update(zip(keys2, vals2))

    return out

st.title("Bulk User-ID Detail Fetcher")

uploaded = st.file_uploader("Upload your input_ids.xlsx", type="xlsx")
if uploaded:
    df_ids = pd.read_excel(uploaded, dtype=str)
    user_ids = df_ids.iloc[:,0].tolist()

    # Login once
    session = requests.Session()
    login_pg = session.get(LOGIN_URL)
    soup_l = BeautifulSoup(login_pg.text, 'html.parser')
    csrf = soup_l.find('input', {'name':'csrfmiddlewaretoken'})['value']
    session.post(
        LOGIN_URL,
        data={'csrfmiddlewaretoken': csrf, 'username': USERNAME, 'password': PASSWORD},
        headers={'Referer': LOGIN_URL}
    )

    # Parallel fetch
    with ThreadPoolExecutor(10) as exe:
        futures = [exe.submit(fetch_user, session, uid) for uid in user_ids]
        results = [f.result() for f in as_completed(futures)]

    out_df = pd.DataFrame(results)
    towrite = out_df.to_excel(index=False, engine='openpyxl')
    st.download_button("Download results.xlsx", towrite, file_name="results.xlsx")
