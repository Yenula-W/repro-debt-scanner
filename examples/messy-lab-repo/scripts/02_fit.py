import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

df = pd.read_csv("clean_counts.csv")
meta = pd.read_csv("data/plate_metadata.csv")
train, test = train_test_split(df)
noise = np.random.normal(size=len(df))
