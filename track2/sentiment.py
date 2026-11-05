import pandas as pd
from transformers import pipeline

def score_sentiments(text, model_name, batch_size, max_length, device):
    '''
    returns dataframe of labelled sentiments + confidence scores for each review
    '''

    clf = pipeline(
        
    )