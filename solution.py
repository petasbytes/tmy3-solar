from datetime import datetime, timedelta
from datetime import timezone
import csv
import json
import matplotlib.pyplot as plt
import pandas as pd
import time
import os


def parse_tmy3_datetime(date_str, time_str):
    """
    Parse TMY3 date and time, converting notation Python-friendly while preserving interval-end semantics.

    Time Semantics:
    - INTERVAL-END: TMY3 timestamps represent the END of a measurement period.
      E.g., "01:00" = end of the hour 00:00-01:00.
    - NOTATION CONVERSION: TMY3 uses 01:00-24:00; Python datetime uses 00:00-23:00.
      Convert while preserving the instant: TMY3's "01/31/1998 24:00" = Python's "1998-02-01 00:00:00".
    """
    # Strip seconds if present
    time_str = time_str[:5]

    # Detect date format (YYYY-MM-DD or MM/DD/YYYY)
    date_fmt = "%Y-%m-%d" if "-" in date_str else "%m/%d/%Y"

    # Handle 24:00 notation (strptime rejects it; convert to next day 00:00)
    if time_str == "24:00":
        dt = datetime.strptime(date_str, date_fmt)
        dt = dt + timedelta(days=1)
    else:
        dt = datetime.strptime(f"{date_str} {time_str}", f"{date_fmt} %H:%M")

    return dt


def convert_local_to_epoch_ms(local_datetime, tz_hours):
    """Convert local datetime to UTC and then to epoch milliseconds."""
    utc_datetime_tznaive = local_datetime - timedelta(seconds=tz_hours * 3600)
    utc_datetime_tzaware = utc_datetime_tznaive.replace(tzinfo=timezone.utc)
    timestamp_ms = int(utc_datetime_tzaware.timestamp() * 1000)
    return timestamp_ms, utc_datetime_tznaive, utc_datetime_tzaware


def calculate_week_bin_from_datetime(dt):
    """Calculate week bin (0-51) from a datetime, based on day-of-year normalization."""
    # Normalize to reference year 1999 (non-leap year) for consistent day-of-year
    # Handle Feb 29 (in the case of python next-day 00:00:00, converted from TMY3 24:00:00 Feb 28) by treating it as Feb 28 for normalization to non-leap year
    month, day = dt.month, dt.day
    if month == 2 and day == 29:
        day = 28

    try:
        normalized_dt = datetime(1999, month, day, dt.hour, dt.minute)
    except ValueError as e:
        print(f"ERROR: {dt} → month={dt.month}, day={dt.day}")
        raise
    day_of_year = normalized_dt.timetuple().tm_yday  # 1-365
    hour_of_day = dt.hour
    hours_since_year_start = (day_of_year - 1) * 24 + hour_of_day
    # 0-51 (with potential 52 for final partial week)
    week_bin = hours_since_year_start // 168
    return week_bin


# Load required station metadata from CSV
stations = {}
with open('TMY3_StationsMeta.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        usaf = row['USAF']
        stations[usaf] = {
            "id": usaf,
            "site_name": row['Site Name'],
            "coordinates": [float(row['Longitude']), float(row['Latitude'])],
            "tz_hours": int(row['TZ'])
        }

# Load required weather data from CSV
start_load = time.time()
print("\nLoading tmy3.csv...")
df = pd.read_csv('tmy3.csv', usecols=[
    'Date (MM/DD/YYYY)',
    'Time (HH:MM)',
    'station_number',
    'GHI (W/m^2)',
    'DNI (W/m^2)'
])
load_time = time.time() - start_load

# Parse datetimes
start_parse = time.time()
df['datetime'] = df.apply(
    lambda row: parse_tmy3_datetime(
        row['Date (MM/DD/YYYY)'], row['Time (HH:MM)']),
    axis=1
)
parse_time = time.time() - start_parse
print(f"Datetime parse time: {parse_time:.1f}s")

start_rowsload = time.time()
rows = df.to_dict('records')
print(f"Rows loaded: {len(rows)}")
rowsload_time = time.time() - start_rowsload
print(f"Rows load time: {rowsload_time:.1f}s")

# Build datetimes list from the parsed column
print("\n\nParse & convert local datetimes (TMY3 notation → Python datetime)...")
datetimes = df['datetime'].tolist()

# Show example conversions (first, middle, last)
print("\n  Example conversions (first, middle, last) in local Python datetime:")
for idx in [0, len(rows)//2, -1]:
    row = rows[idx]
    original = f"{row['Date (MM/DD/YYYY)']} {row['Time (HH:MM)']}"
    print(f"    {original} → {datetimes[idx]}")

print(f"\n  Min (local Python datetime): {datetimes[0]}")
print(f"  Max (local Python datetime): {datetimes[-1]}")

# Check required columns
print("\n\nValidate required columns...")
required = ['Date (MM/DD/YYYY)', 'Time (HH:MM)',
            'station_number', 'GHI (W/m^2)', 'DNI (W/m^2)']
for col in required:
    present = col in df.columns
    print(f"  {col}: {'✓' if present else '✗'}")

print(f"\nLoad time: {load_time:.1f}s")
print(f"Parse completed without errors")

# Add timezone, site_name, coordinates columns to each row
df['tz_hours'] = df['station_number'].apply(
    lambda x: stations[str(x)]['tz_hours'])
df['site_name'] = df['station_number'].apply(
    lambda x: stations[str(x)]['site_name'])
df['coordinates'] = df['station_number'].apply(
    lambda x: stations[str(x)]['coordinates'])

# Validate metadata join
print("\n\nValidate metadata join...")
weather_stations = set(df['station_number'].unique())
metadata_stations = set(stations.keys())
weather_stations_int = {int(s) for s in weather_stations}
metadata_stations_int = {int(s) for s in metadata_stations}

print(f"  Weather stations in data: {len(weather_stations_int)}")
print(f"  Metadata stations available: {len(metadata_stations_int)}")

missing = weather_stations_int - metadata_stations_int
if missing:
    print(f"  Missing from metadata: {missing} ✗")
else:
    print(f"  All weather stations found in metadata: ✓")

print(f"  Rows enriched with metadata: {len(df)} ✓")

# Weekly binning and aggregation (7-day intervals based on day-of-year, independent of year)
print("\n\nWeekly binning and aggregation (day-of-year based, 7-day intervals)...")

# Step 1: Add week_bin column via pandas
start_week = time.time()
df['week_bin'] = df['datetime'].apply(calculate_week_bin_from_datetime)
week_time = time.time() - start_week
print(f"Week binning time: {week_time:.1f}s")

# Detect nulls in GHI/DNI before filling
null_ghi = df['GHI (W/m^2)'].isnull().sum()
null_dni = df['DNI (W/m^2)'].isnull().sum()

if null_ghi > 0 or null_dni > 0:
    print("\n\nDetected null GHI/DNI values:")
    null_mask = df['GHI (W/m^2)'].isnull() | df['DNI (W/m^2)'].isnull()
    null_rows = df[null_mask][['station_number', 'datetime',
                               'GHI (W/m^2)', 'DNI (W/m^2)']].sort_values('datetime')
    for _, row in null_rows.iterrows():
        print(
            f"  Station {row['station_number']} @ {row['datetime']} → GHI={row['GHI (W/m^2)']}, DNI={row['DNI (W/m^2)']}")
    print(f"\nFilling {null_ghi} GHI + {null_dni} DNI nulls with 0...")

# Fill null GHI/DNI with 0
df['GHI (W/m^2)'] = df['GHI (W/m^2)'].fillna(0)
df['DNI (W/m^2)'] = df['DNI (W/m^2)'].fillna(0)
print(f"    ...done")

first_5_stations = sorted(df['station_number'].unique())[:5]

print("\n  Weekly row counts (first 5 stations):")
all_week_counts = df.groupby(['station_number', 'week_bin']).size()
for station_id in first_5_stations:
    station_df = df[df['station_number'] == station_id]
    week_counts = station_df.groupby('week_bin').size()
    print(f"  Station {station_id}:")
    for week_bin in sorted(week_counts.index):
        print(f"    Week {week_bin} → {week_counts[week_bin]} rows")

total_rows = len(df)
max_weeks = df.groupby('station_number')['week_bin'].max().max() + 1
print(f"\n    Max weeks (per station): {max_weeks}")
print(f"    Total rows accounted for: {total_rows} / {len(df)} ✓")

# Step 2: Calculate GHI and DNI averages for each station's week bin
print("\n  GHI & DNI averages by week:")
for station_id in first_5_stations:
    station_df = df[df['station_number'] == station_id]
    weekly_agg = station_df.groupby('week_bin').agg({
        'GHI (W/m^2)': 'mean',
        'DNI (W/m^2)': 'mean'
    })
    print(f"  Station {station_id}:")
    for week_bin in sorted(weekly_agg.index):
        ghi_avg = weekly_agg.loc[week_bin, 'GHI (W/m^2)']
        dni_avg = weekly_agg.loc[week_bin, 'DNI (W/m^2)']
        print(
            f"    Week {week_bin} → GHI: {ghi_avg:.1f} W/m², DNI: {dni_avg:.1f} W/m²")

# Spot check: first week's calculation
first_station_id = sorted(df['station_number'].unique())[0]
first_week_bin = sorted(df['week_bin'].unique())[0]
print(
    f"\n  Spot check (first week, station {first_station_id}, week_bin {first_week_bin}):")
first_week_data = df[(df['station_number'] == first_station_id) & (
    df['week_bin'] == first_week_bin)].sort_values('datetime')
first_week_ghi = first_week_data['GHI (W/m^2)'].tolist()
first_week_dni = first_week_data['DNI (W/m^2)'].tolist()
print(f"    GHI values by day (24 hours/day):")
for day in range(7):
    day_values = first_week_ghi[day*24:(day+1)*24]
    print(f"      Day {day+1}: {day_values}")
print(f"    GHI count: {len(first_week_ghi)}")
print(f"    GHI sum: {sum(first_week_ghi)}")
print(f"    GHI average: {sum(first_week_ghi) / len(first_week_ghi):.1f} W/m²")

print(f"    DNI values by day (24 hours/day):")
for day in range(7):
    day_values = first_week_dni[day*24:(day+1)*24]
    print(f"      Day {day+1}: {day_values}")
print(f"    DNI count: {len(first_week_dni)}")
print(f"    DNI sum: {sum(first_week_dni)}")
print(f"    DNI average: {sum(first_week_dni) / len(first_week_dni):.1f} W/m²")

# Build output records
output = []
for station_id in sorted(df['station_number'].unique()):
    station_df = df[df['station_number'] == station_id]

    station_df['normalized_doy_hour'] = station_df['datetime'].apply(
        lambda dt: (datetime(1999, dt.month, dt.day if dt.day <
                    29 else 28).timetuple().tm_yday * 24 + dt.hour)
    )

    station_df = station_df.sort_values('normalized_doy_hour')
    # Get weekly aggregates for this station (with last datetime)
    weekly_agg_with_dt = station_df.groupby('week_bin').agg({
        'GHI (W/m^2)': 'mean',
        'DNI (W/m^2)': 'mean',
        'datetime': 'last'
    })

    output_records = []
    for week_bin in sorted(weekly_agg_with_dt.index):
        ghi_avg = weekly_agg_with_dt.loc[week_bin, 'GHI (W/m^2)']
        dni_avg = weekly_agg_with_dt.loc[week_bin, 'DNI (W/m^2)']
        last_original_dt = weekly_agg_with_dt.loc[week_bin,
                                                  'datetime'] + timedelta(hours=1)

        # Convert local Python datetime → UTC → epoch ms
        timestamp_ms, _, _ = convert_local_to_epoch_ms(
            last_original_dt, int(station_df['tz_hours'].iloc[0]))

        # Spot-check: verify timezone conversion for first week, first 5 stations
        if station_id in first_5_stations and week_bin == 0:
            utc_dt = last_original_dt - \
                timedelta(hours=int(station_df['tz_hours'].iloc[0]))
            print(
                f"\n  Verify timezone conversion - first week (station {station_id}):")
            print(f"    Week-end datetime (local): {last_original_dt}")
            print(
                f"    Station TZ offset: {int(station_df['tz_hours'].iloc[0])} hours")
            print(f"    UTC datetime: {utc_dt}")
            print(f"    Epoch milliseconds: {timestamp_ms}")

        output_records.append({
            # "week_bin": week_bin,  # DEBUG
            "timestamp": timestamp_ms,
            "ghi": round(ghi_avg, 1),
            "dni": round(dni_avg, 1)
        })

    # Build output JSON
    output.append({
        "id": str(station_id),
        "site_name": station_df['site_name'].iloc[0],
        "coordinates": station_df['coordinates'].iloc[0],
        "data": output_records
    })

# Write to file
start_json = time.time()
with open('output.json', 'w') as f:
    json.dump(output, f, indent=2)
json_time = time.time() - start_json
print(f"JSON write time: {json_time:.1f}s")

print(f"\n\nPreparing JSON file...")
print(
    f"\n  ✓ output.json written ({len(output)} stations, {len(output[0]['data'])} weeks per station)")
print(f"  JSON file size: {os.path.getsize('output.json'):,} bytes")

# Visualize weekly GHI and DNI
print(f"\n\nGenerating visualisation for first 5 stations...")
for station_record in output[:5]:
    station_id = station_record['id']
    site_name = station_record['site_name']
    output_records = station_record['data']

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))

    week_indices = range(len(output_records))
    ghi_values = [rec['ghi'] for rec in output_records]
    dni_values = [rec['dni'] for rec in output_records]

    ax1.plot(week_indices, ghi_values, marker='o',
             linestyle='-', color='orange', linewidth=2)
    ax1.set_ylabel('GHI (W/m²)', fontsize=11)
    ax1.set_title(f'{site_name} - Weekly Averages',
                  fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)

    ax2.plot(week_indices, dni_values, marker='o',
             linestyle='-', color='red', linewidth=2)
    ax2.set_xlabel('Week', fontsize=11)
    ax2.set_ylabel('DNI (W/m²)', fontsize=11)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    filename = f'output_{station_id}.png'
    plt.savefig(filename, dpi=100, bbox_inches='tight')
    print(f"✓ {filename} saved")
    plt.close()

print()
