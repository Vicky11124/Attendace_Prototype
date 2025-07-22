import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, time

st.set_page_config(page_title="College Staff Attendance Dashboard", layout="wide")
st.title("College Staff Attendance Dashboard")

# ---------- Feature Engineering for both Excel and CSV ----------
def feature_engineering(df):
    df = df.copy()
    df['Shift'] = df['Shift'].fillna('GS')
    df['InTime'] = df['InTime'].fillna('').str.strip()
    def parse_time(s):
        try:
            if s and ':' in s:
                return datetime.strptime(s, '%H:%M:%S').time()
        except Exception:
            return np.nan
        return np.nan
    df['InTime_obj'] = df['InTime'].apply(parse_time)
    df['TotDur'] = df['Tot.  Dur.'].fillna('').str.strip() if 'Tot.  Dur.' in df.columns else ''
    def parse_dur(s):
        for fmt in ('%H:%M:%S','%H:%M'):
            try:
                if s and ':' in s:
                    t = datetime.strptime(s, fmt)
                    return t.hour*60 + t.minute
            except: continue
        return np.nan
    df['TotDur_min'] = df['TotDur'].apply(parse_dur) if 'TotDur' in df else df.get('TotDur_min', pd.Series(np.nan, index=df.index))
    def delay(row):
        sched = time(9,0,0)
        t = row['InTime_obj']
        if t is not np.nan and pd.notnull(t):
            return (t.hour-sched.hour)*60 + (t.minute-sched.minute)
        return np.nan
    df['Delay_Minutes'] = df.apply(delay, axis=1)
    df['Delay_Flag'] = (df['Delay_Minutes'] > 0).astype(int)
    scheduled_duration = 6 * 60  # 6 hours 9:00-15:00
    df['Early_Leave_Min'] = df['TotDur_min'].apply(lambda x: scheduled_duration-x if pd.notnull(x) and x < scheduled_duration else 0)
    df['Overtime_Min'] = df['TotDur_min'].apply(lambda x: x-scheduled_duration if pd.notnull(x) and x > scheduled_duration else 0)
    df['Is_Absent'] = df.get('Status','').fillna('').str.contains("Absent",case=False).astype(int)
    df['Is_Present'] = df.get('Status','').fillna('').str.contains("Present",case=False).astype(int)
    df['Is_Half_Day'] = df.get('Status','').fillna('').str.contains("½Present",case=False).astype(int)
    df['Has_Permission'] = df.get('Remarks','').fillna('').str.lower().str.contains("permission").astype(int)
    # Columns to show
    display_cols = [
        "Department", "E. Code", "Name", "Shift", "InTime", "Delay_Minutes", "Delay_Flag",
        "TotDur_min", "Early_Leave_Min", "Overtime_Min",
        "Is_Absent", "Is_Present", "Is_Half_Day", "Has_Permission", "Status", "Remarks"
    ]
    for col in display_cols:
        if col not in df.columns: df[col] = np.nan
    return df[display_cols]

# ---------- Excel Block Parser ----------
def process_attendance_excel(df_raw):
    tables = []
    i = 0
    while i < len(df_raw):
        if df_raw.iloc[i].astype(str).str.fullmatch("Department", na=False).any():
            dept_row = df_raw.iloc[i]
            dept_name = None
            for v in dept_row.values:
                if isinstance(v, str) and v.strip() not in ["", "Department"]:
                    dept_name = v.strip()
                    break
            header_row = i + 1
            data_start = header_row + 1
            data_end = data_start
            header_vals = df_raw.iloc[header_row].tolist()
            cols_used = [j for j, v in enumerate(header_vals) if isinstance(v, str) and v.strip() != ""]
            if not cols_used:
                i += 1
                continue
            last_col = max(cols_used)
            headers = [
                header_vals[j] if header_vals[j] == header_vals[j] and str(header_vals[j]).strip() != ''
                else f'unnamed_{j}'
                for j in range(last_col + 1)
            ]
            while data_end < len(df_raw) and not df_raw.iloc[data_end].astype(str).str.fullmatch("Department", na=False).any():
                data_end += 1
            datablock = df_raw.iloc[data_start:data_end, :last_col + 1].copy()
            datablock.columns = headers
            datablock["Department"] = dept_name
            if 'E. Code' in datablock.columns:
                datablock = datablock[datablock["E. Code"].notnull() & (datablock["E. Code"].str.strip() != "")]
                if not datablock.empty:
                    tables.append(datablock.reset_index(drop=True))
            i = data_end
        else:
            i += 1
    if not tables:
        st.error("No department attendance tables found! Please check your Excel file format.")
        return pd.DataFrame()
    df = pd.concat(tables, ignore_index=True)
    return feature_engineering(df)

# ---------- File Upload Section ----------
uploaded = st.file_uploader("Upload your attendance file (.xlsx or .csv):", type=["xlsx", "csv"])
if uploaded:
    filetype = uploaded.name.split('.')[-1].lower()
    if filetype == "xlsx":
        raw_df = pd.read_excel(uploaded, header=None, dtype=str)
        df = process_attendance_excel(raw_df)
    elif filetype == "csv":
        df = pd.read_csv(uploaded)
        df = feature_engineering(df)
    else:
        st.error("Unsupported file format. Please upload an Excel (.xlsx) or CSV (.csv) file.")
        st.stop()

    if df is not None and not df.empty:
        # Sidebar filters
        departments = sorted(df['Department'].dropna().unique())
        dept_choice = st.sidebar.selectbox("Select Department", ["All"] + departments)
        search_code = st.sidebar.text_input("Search by Staff Code or Name", "")

        filtered_df = df.copy()
        if dept_choice != "All":
            filtered_df = filtered_df[filtered_df['Department'] == dept_choice]
        if search_code:
            filtered_df = filtered_df[
                filtered_df['E. Code'].astype(str).str.contains(search_code, case=False, na=False) |
                filtered_df['Name'].astype(str).str.contains(search_code, case=False, na=False)
            ]

        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Staff Shown", len(filtered_df))
        with col2:
            st.metric("Present", int(filtered_df["Is_Present"].sum()))
        with col3:
            st.metric("Absent", int(filtered_df["Is_Absent"].sum()))
        with col4:
            st.metric("With Permission", int(filtered_df["Has_Permission"].sum()))

        st.dataframe(filtered_df, use_container_width=True)

        # Delay/Latecomer Analysis
        if st.checkbox("Show Delay/Latecomer Analysis"):
            late_df = filtered_df[filtered_df["Delay_Flag"] == 1]
            st.write(f"**Number of Late Staff:** {len(late_df)}")
            if not late_df.empty:
                st.table(
                    late_df[["Department", "E. Code", "Name", "Shift", "InTime", "Delay_Minutes"]]
                    .sort_values("Delay_Minutes", ascending=False)
                )
                st.bar_chart(late_df.groupby("Department")["Delay_Flag"].sum())

        # Department-wise Summary
        if st.checkbox("Show Department-wise Summary"):
            st.bar_chart(df.groupby("Department")["Is_Present"].sum())

        st.caption(
            "Tip: Filter by department/sidebar for focused staff lists or search by partial name/code for details."
        )
else:
    st.info("Please upload your attendance file (Excel or CSV) to begin analysis.")

