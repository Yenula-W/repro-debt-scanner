import pandas as pd

raw = pd.read_csv("/Users/alice/Dropbox/lab/raw_counts.csv")
raw.dropna().to_csv("clean_counts.csv")
