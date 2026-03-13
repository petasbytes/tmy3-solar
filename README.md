# TMY3 GHI & DNI Weekly Aggregation

Read hourly solar weather data from TMY3 CSV files, compute weekly average GHI and DNI for each station, output to JSON.

## Requirements
- Python 3.7+
- pandas
- matplotlib

## Setup
```bash
# Install uv if needed
pip install uv

# Install dependencies
uv sync
```

## Run
```bash
uv run solution.py
```

Expects `tmy3.csv` and `TMY3_StationsMeta.csv` in current directory.

Output:
- `output.json` (1,020 stations, 53 weeks each, ~5 MB)
- PNG visualizations for first 5 stations

## Data Files

Download `tmy3.csv` and `TMY3_StationsMeta.csv` from [Kaggle TMY3 dataset](https://www.kaggle.com/datasets/us-doe/tmy3-solar/data). Place in the same directory as `solution.py`.

## Output Format

See `output_sample.json` for an example (3 of 1,020 stations). Full output contains all stations with the same structure:

```json
[
  {
    "id": "<station ID>",
    "site_name": "<station name>",
    "coordinates": [<longitude>, <latitude>],
    "data": [
      {
        "timestamp": 1234567890000,
        "ghi": 120.5,
        "dni": 95.2
      },
      ...
    ]
  },
  ...
]
```
