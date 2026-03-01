import streamlit as st
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules

def one_hot_from_transactions(df, transaction_col, item_col):
    df = df[[transaction_col, item_col]].dropna()
    df[item_col] = df[item_col].astype(str)
    df[transaction_col] = df[transaction_col].astype(str)
    mat = df.drop_duplicates().assign(v=1).pivot_table(index=transaction_col, columns=item_col, values='v', fill_value=0)
    return mat.astype(bool)

def normalize_one_hot(df):
    df = df.fillna(0)
    for c in df.columns:
        df[c] = df[c].astype(int).clip(0, 1).astype(bool)
    return df

def build_sample():
    data = [
        ('T1', 'Milk'), ('T1', 'Bread'), ('T1', 'Butter'),
        ('T2', 'Bread'), ('T2', 'Butter'),
        ('T3', 'Milk'), ('T3', 'Bread'),
        ('T4', 'Bread'), ('T4', 'Butter'), ('T4', 'Jam'),
        ('T5', 'Milk'), ('T5', 'Bread'), ('T5', 'Butter'), ('T5', 'Eggs')
    ]
    return pd.DataFrame(data, columns=['Transaction', 'Item'])

def stringify_itemset(s):
    return ', '.join(sorted(list(s)))

st.set_page_config(page_title='Market Basket Analysis', layout='wide')
st.title('Market Basket Analysis')

st.sidebar.header('Parameters')
min_support = st.sidebar.slider('Min Support', 0.0, 1.0, 0.2, 0.01)
min_confidence = st.sidebar.slider('Min Confidence', 0.0, 1.0, 0.5, 0.01)
min_lift = st.sidebar.slider('Min Lift', 1.0, 10.0, 1.2, 0.1)
max_len = st.sidebar.slider('Max Itemset Size', 1, 5, 3, 1)

st.sidebar.header('Data')
use_sample = st.sidebar.checkbox('Use sample data', value=True)
input_type = st.sidebar.radio('Input Type', ['Transactions (two columns)', 'One-hot (columns are items)'])

uploaded = st.file_uploader('Upload CSV', type=['csv'])

df_raw = None
if use_sample:
    df_raw = build_sample()
elif uploaded:
    df_raw = pd.read_csv(uploaded)

if df_raw is None:
    st.info('Upload a dataset or enable sample data.')
    st.stop()

st.subheader('Raw Data')
st.dataframe(df_raw.head(50))

one_hot = None
if input_type == 'Transactions (two columns)':
    cols = list(df_raw.columns)
    if len(cols) < 2:
        st.error('Transactions input requires at least two columns.')
        st.stop()
    transaction_col = st.selectbox('Transaction ID column', cols, index=0)
    item_col = st.selectbox('Item column', cols, index=1)
    one_hot = one_hot_from_transactions(df_raw, transaction_col, item_col)
else:
    one_hot = normalize_one_hot(df_raw)

st.subheader('Transactions x Items')
st.dataframe(one_hot.astype(int).head(50))

frequent_itemsets = apriori(one_hot, min_support=min_support, use_colnames=True, max_len=max_len)
frequent_itemsets['length'] = frequent_itemsets['itemsets'].apply(lambda s: len(s))
frequent_itemsets['itemset'] = frequent_itemsets['itemsets'].apply(stringify_itemset)

st.subheader('Frequent Itemsets')
st.dataframe(frequent_itemsets[['itemset', 'support', 'length']].sort_values(['support', 'length'], ascending=[False, True]).reset_index(drop=True))

rules = association_rules(frequent_itemsets, metric='confidence', min_threshold=min_confidence)
rules = rules[rules['lift'] >= min_lift].copy()
rules['antecedents_str'] = rules['antecedents'].apply(stringify_itemset)
rules['consequents_str'] = rules['consequents'].apply(stringify_itemset)
rules_view = rules[['antecedents_str', 'consequents_str', 'support', 'confidence', 'lift', 'conviction']].sort_values(['confidence', 'lift'], ascending=[False, False]).reset_index(drop=True)

st.subheader('Association Rules')
st.dataframe(rules_view)

st.subheader('Charts')
top_n = st.slider('Top N frequent itemsets', 5, 50, 15, 1)
st.bar_chart(frequent_itemsets[['itemset', 'support']].sort_values('support', ascending=False).head(top_n).set_index('itemset'))

st.subheader('Download')
csv_itemsets = frequent_itemsets[['itemset', 'support', 'length']].to_csv(index=False).encode('utf-8')
st.download_button('Download Itemsets CSV', csv_itemsets, 'frequent_itemsets.csv', 'text/csv')
csv_rules = rules_view.to_csv(index=False).encode('utf-8')
st.download_button('Download Rules CSV', csv_rules, 'association_rules.csv', 'text/csv')
