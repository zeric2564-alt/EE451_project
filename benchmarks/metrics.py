"""Definitions shared by the report and numerical edge-case tests."""
import statistics as st

def percentile(values,p):
    if not values or not 0<=p<=1:raise ValueError('nonempty data and quantile in [0,1] required')
    values=sorted(values);i=(len(values)-1)*p;j=int(i)
    return values[j]+(values[min(j+1,len(values)-1)]-values[j])*(i-j)

def regional_ratio(values):
    low=percentile(values,.1);high=percentile(values,.9);mean=st.mean(values)
    if low>0:return 'P90/P10',high/low
    if mean>0:return 'max/mean',max(values)/mean
    return 'all zero',None
