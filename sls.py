import bisect
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

def _compute_coef_matrix(w):
    from numpy import array, arange, ones, linalg, eye
    X = array([arange(w), ones([w])]).transpose()
    return X @ linalg.inv(X.transpose() @ X) @ X.transpose() - eye(w)

def _partition_anomalies(windows, k):
    diffs = [windows[iw - 1][1] - windows[iw][1]
             for iw in range(1, len(windows))]
    top_jump_positions = sorted(range(len(diffs)), key=lambda i: diffs[i], reverse=True)[0:k-1]
    return sorted(top_jump_positions) + [len(windows) - 1]

def detect_anomalies(data, lag, num_anomalies, num_levels=5, visualize=True):
    if type(data) != pd.Series:
        raise ValueError('data must be of the pandas Series type')
    if lag < 3:
        raise ValueError('lag needs to be at least 3.')
    if num_anomalies < 0:
        raise ValueError('expected number of anomalies must be positive.')
    num_levels = min(num_levels, num_anomalies) 

    data = data.fillna(method='pad')

    coefs = _compute_coef_matrix(lag)

    values = data.values
    num_windows = len(values) - lag + 1
    windows = np.vstack(values[ix:ix + num_windows] for ix in range(lag))
    residuals = np.linalg.norm(coefs @ windows, axis=0)

    windows = [(ix, residuals[ix]) for ix in range(num_windows)]
    windows.sort(key=lambda item: item[1], reverse=True)

    if num_anomalies == 0 or num_levels == 0:
        max_anomaly_score = windows[0][1]
        if visualize:
            print(
                'The maximum anomaly score in the training data is {0:2f}. '
                'Since you specified no anomaly observed in the historical data, the recommended threshold is {1:2f}'
                    .format(max_anomaly_score, max_anomaly_score * 2))
        return None, [max_anomaly_score * 2]

    iw = 0
    top_iws = [iw]
    while len(top_iws) < num_anomalies:
        while iw < num_windows and any(abs(windows[jw][0] - windows[iw][0]) < lag for jw in top_iws):
            iw += 1
        if iw < num_windows:
            top_iws.append(iw)
            iw += 1
        else:
            break
    results = [windows[iw] for iw in top_iws]

    partition_points = _partition_anomalies(results, num_levels)
    thresholds = [results[iw][1] - 1e-3 for iw in partition_points]

    timestamps = data.index
    anomalies = []
    rank = 0
    for level, limit in enumerate(partition_points):
        while rank <= limit:
            iw = results[rank][0]
            anomalies.append((num_levels - level, str(timestamps[iw]), str(timestamps[iw + lag - 1]), results[rank][1]))
            rank += 1
    anomalies = pd.DataFrame(anomalies, columns=['level', 'start', 'end', 'score'])

    if visualize:
        from IPython.display import display
        display(anomalies)

        data.plot(title='lag: {0}, #levels: {1}, #anomalies: {2}'
                  .format(lag, num_levels, num_anomalies))
        for anomaly in anomalies.values:

            #problem 3
            start_time = pd.to_datetime(anomaly[1])
            end_time = pd.to_datetime(anomaly[2])

            # use mdates to avoid timezone issues
            start_time_num = mdates.date2num(start_time.to_pydatetime())
            end_time_num = mdates.date2num(end_time.to_pydatetime())

            color = plt.cm.jet(0.65 + float(anomaly[0]) / num_levels / 3)
            width = end_time_num - start_time_num
            rect = Rectangle((start_time_num, plt.ylim()[0]), width, plt.ylim()[1] - plt.ylim()[0], color=color, alpha=0.5)
            
            plt.gca().add_patch(rect)

    return anomalies, thresholds

def anomalies_to_series(anomalies, index):
    rows = anomalies.shape[0]
    series = pd.Series(np.zeros(len(index)), dtype=np.int)
    series.index = index
    for r in range(rows):
        start = anomalies.loc[r, 'start']
        end = anomalies.loc[r, 'end']
        level = int(anomalies.loc[r, 'level'])
        series[start:end] = level
    return series

class StreamingAnomalyDetector:
    def __init__(self, lag, thresholds):
        self._w = lag
        self._thresholds = thresholds
        self._buffer = np.array([float('nan')] * lag)
        self._buffer.shape = (lag, 1)  # make it vertical
        self._coef_matrix = _compute_coef_matrix(lag)

    def update_thresholds(self, thresholds):
        self._thresholds = thresholds

    def score(self, value):
        self._buffer[:-1] = self._buffer[1:]
        self._buffer[-1] = value
        return np.linalg.norm(self._coef_matrix @ self._buffer)

    def classify(self, value):
        return bisect.bisect_left(self._thresholds, self.score(self, value))
