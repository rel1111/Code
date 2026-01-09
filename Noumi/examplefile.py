#pip install streamlit pandas numpy matplotlib openpyxl pytz
#test
#test 
import streamlit as st
import io
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.dates as mdates
from datetime import timedelta, datetime
import pytz
import textwrap
#testest
def normalize_columns(df):
    """Standardize column names to lower-case with spaces."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    mapping = {
        'product name': 'product name',
        'quantity liters': 'quantity liters',
        'process speed per hour': 'process speed per hour',
        'qty of batch': 'qty of batch',
        'date from': 'date from',
        'first wash time': 'first wash time',
        'gap': 'gap',
        'intermediate wash duration': 'intermediate wash duration',
        'duration': 'duration',
        'changeover duration': 'changeover duration',
        'change over': 'changeover duration',
        'full gap': 'full gap',
        'intermediate gap': 'intermediate gap',
        'title': 'title',
        'additional wash': 'additional wash',
        'line efficiency': 'line efficiency'
    }
    df.rename(columns={k: v for k, v in mapping.items() if k in df.columns}, inplace=True)
    return df

def parse_datetime(value, label):
    """Parse a datetime-like value safely, returning NaT for unparseable values."""
    try:
        dt_value = pd.to_datetime(value, errors='coerce')
        if pd.isna(dt_value):
            if value is not None and not (isinstance(value, float) and math.isnan(value)):
                st.warning(f"Could not parse '{label}' datetime: {value}. Treating as missing.")
        return dt_value
    except Exception as e:
        st.warning(f"Unexpected error parsing '{label}' datetime: {value} ({e}). Returning NaT.")
        return pd.NaT

def ensure_required_columns(df):
    required = [
        'product name', 'quantity liters', 'process speed per hour',
        'qty of batch', 'date from', 'first wash time', 'gap',
        'intermediate wash duration', 'duration', 'line efficiency'
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}\nPresent columns: {list(df.columns)}")

def schedule_plan(df):
    """Build schedule based on processing logic with wash timing."""
    df = df.copy()
    df = normalize_columns(df)
    ensure_required_columns(df)

    start_time = parse_datetime(df.loc[0, 'date from'], 'Date From')
    first_full_time = parse_datetime(df.loc[0, 'first wash time'], 'First Wash Time')

    if pd.isna(first_full_time):
        current_time = start_time
    else:
        current_time = min(start_time, first_full_time)

    if 'intermediate gap' in df.columns:
        inter_gap_min = float(df.loc[0, 'intermediate gap'])
    else:
        inter_gap_min = 1440.0

    full_gap_min = float(df.loc[0, 'full gap']) if 'full gap' in df.columns else float(df.loc[0, 'gap'])

    inter_wash_dur_min = float(df.loc[0, 'intermediate wash duration'])
    full_wash_dur_min = float(df.loc[0, 'duration'])

    first_full_done = False
    processed_since_inter_reset = 0.0
    processed_since_full_reset = 0.0

    segments = []
    batch_marks = []

    def _add_segment_with_merge_logic(product_idx, product_name, start, end, kind):
        nonlocal segments
        new_start_dt = pd.to_datetime(start)
        new_end_dt = pd.to_datetime(end)
        new_segment_candidate = {
            'product_idx': product_idx,
            'product_name': product_name,
            'start': new_start_dt,
            'end': new_end_dt,
            'kind': kind
        }

        if segments:
            last_segment = segments[-1]
            last_end_dt = last_segment['end']

            if last_end_dt == new_start_dt:
                is_last_wash = 'wash' in last_segment['kind']
                is_new_wash = 'wash' in new_segment_candidate['kind']
                is_last_changeover = last_segment['kind'] == 'changeover'
                is_new_changeover = new_segment_candidate['kind'] == 'changeover'

                if (is_last_changeover and is_new_wash) or (is_last_wash and is_new_changeover):
                    last_duration = (last_segment['end'] - last_segment['start']).total_seconds()
                    new_duration = (new_segment_candidate['end'] - new_segment_candidate['start']).total_seconds()

                    merged_start = last_segment['start']
                    merged_end = new_segment_candidate['end']

                    if last_duration >= new_duration:
                        dominant_segment = last_segment
                    else:
                        dominant_segment = new_segment_candidate

                    merged_kind = dominant_segment['kind']

                    if 'wash' in merged_kind:
                        merged_product_idx = None
                        merged_product_name = 'WASH'
                    elif merged_kind == 'changeover':
                        merged_product_idx = dominant_segment['product_idx']
                        merged_product_name = dominant_segment['product_name']
                    else:
                        merged_product_idx = dominant_segment['product_idx']
                        merged_product_name = dominant_segment['product_name']

                    segments[-1] = {
                        'product_idx': merged_product_idx,
                        'product_name': merged_product_name,
                        'start': merged_start,
                        'end': merged_end,
                        'kind': merged_kind
                    }
                    return

        segments.append(new_segment_candidate)

    def maybe_first_full_wash_block():
        nonlocal current_time, first_full_done, processed_since_inter_reset, processed_since_full_reset
        if pd.notna(first_full_time) and not first_full_done and current_time >= first_full_time:
            fw_start = current_time
            fw_end = fw_start + timedelta(minutes=full_wash_dur_min)
            iw_start = fw_start
            iw_end = iw_start + timedelta(minutes=inter_wash_dur_min)
            pause_end = max(fw_end, iw_end)
            _add_segment_with_merge_logic(None, 'WASH', fw_start, fw_end, 'full wash')
            _add_segment_with_merge_logic(None, 'WASH', iw_start, iw_end, 'intermediate wash')
            processed_since_inter_reset = 0.0
            processed_since_full_reset = 0.0
            first_full_done = True
            current_time = pause_end

    maybe_first_full_wash_block()

    if not first_full_done and pd.isna(first_full_time) and len(df) > 0:
        first_product_changeover_min = 0.0
        if 'changeover duration' in df.columns and pd.notna(df.loc[0, 'changeover duration']):
            first_product_changeover_min = float(df.loc[0, 'changeover duration'])

        if first_product_changeover_min > 0:
            co_start = current_time
            co_end = co_start + timedelta(minutes=first_product_changeover_min)
            _add_segment_with_merge_logic(0, str(df.loc[0, 'product name']), co_start, co_end, 'changeover')
            current_time = co_end

    for i, row in df.iterrows():
        pname = str(row['product name'])
        qty_liters = float(row['quantity liters'])
        speed_lph = float(row['process speed per hour'])
        batch_size_liters = float(row['qty of batch']) if row['qty of batch'] not in [None, np.nan] else 0.0

        try:
            line_efficiency = float(row['line efficiency'])
            if not (0 < line_efficiency <= 1.0):
                raise ValueError("Line efficiency must be between 0 and 1")
        except (ValueError, TypeError, KeyError):
            line_efficiency = 1.0

        changeover_min = float(row['changeover duration']) if 'changeover duration' in row and row['changeover duration'] not in [None, np.nan] else 0.0

        row_start_dt = parse_datetime(row['date from'], f"Date From (row {i})")
        if current_time < row_start_dt:
            current_time = row_start_dt
            processed_since_inter_reset = 0.0
            processed_since_full_reset = 0.0

        if i > 0 and changeover_min > 0:
            co_start = current_time
            co_end = co_start + timedelta(minutes=changeover_min)
            _add_segment_with_merge_logic(i, pname, co_start, co_end, 'changeover')
            current_time = co_end
            processed_since_inter_reset += changeover_min
            processed_since_full_reset += changeover_min

        if 'additional wash' in row and str(row['additional wash']).lower() == 'yes':
            aw_start = current_time
            aw_end = aw_start + timedelta(minutes=full_wash_dur_min)
            _add_segment_with_merge_logic(None, 'WASH', aw_start, aw_end, 'full wash')
            current_time = aw_end
            processed_since_inter_reset = 0.0
            processed_since_full_reset = 0.0

        if speed_lph <= 0:
            raise ValueError(f"Process speed per hour must be > 0 for product '{pname}'")

        effective_speed_lph = speed_lph * line_efficiency
        if effective_speed_lph <= 0:
            raise ValueError(f"Effective process speed per hour must be > 0 for product '{pname}'")

        run_minutes_total = (qty_liters / effective_speed_lph) * 60.0
        run_minutes_remaining = run_minutes_total
        processed_minutes_this_product = 0.0

        batch_thresholds = []
        if batch_size_liters > 0:
            batch_time_min = (batch_size_liters / effective_speed_lph) * 60.0
            num_batches = math.ceil(qty_liters / batch_size_liters)
            for k in range(1, num_batches + 1):
                batch_thresholds.append(k * batch_time_min)

        def handle_batch_marks_in_chunk(chunk_start, chunk_minutes, proc_start_min):
            nonlocal batch_marks
            proc_end_min = proc_start_min + chunk_minutes
            for bt in batch_thresholds:
                if proc_start_min < bt <= proc_end_min + 1e-9:
                    offset_min = bt - proc_start_min
                    mark_time = chunk_start + timedelta(minutes=offset_min)
                    label = f"B{int(round(bt / batch_time_min))}"
                    batch_marks.append({
                        'product_idx': i,
                        'product_name': pname,
                        'time': mark_time,
                        'label': label
                    })

        while run_minutes_remaining > 1e-9:
            proc_minutes_before_this_chunk = processed_minutes_this_product

            if not first_full_done and pd.notna(first_full_time) and current_time < first_full_time:
                allowed_minutes_before_first_full = max(0.0, (first_full_time - current_time).total_seconds() / 60.0)
                chunk_to_process = min(run_minutes_remaining, allowed_minutes_before_first_full)

                if chunk_to_process > 1e-9:
                    prod_start = current_time
                    prod_end = prod_start + timedelta(minutes=chunk_to_process)
                    _add_segment_with_merge_logic(i, pname, prod_start, prod_end, 'production')
                    handle_batch_marks_in_chunk(prod_start, chunk_to_process, proc_minutes_before_this_chunk)

                    current_time = prod_end
                    run_minutes_remaining -= chunk_to_process
                    processed_minutes_this_product += chunk_to_process

                if current_time >= first_full_time:
                    maybe_first_full_wash_block()
                continue

            to_next_inter = inter_gap_min - processed_since_inter_reset
            to_next_full = full_gap_min - processed_since_full_reset

            chunk_to_process = min(run_minutes_remaining, to_next_inter, to_next_full)

            if chunk_to_process > 1e-9:
                prod_start = current_time
                prod_end = prod_start + timedelta(minutes=chunk_to_process)
                _add_segment_with_merge_logic(i, pname, prod_start, prod_end, 'production')
                handle_batch_marks_in_chunk(prod_start, chunk_to_process, proc_minutes_before_this_chunk)

                current_time = prod_end
                run_minutes_remaining -= chunk_to_process
                processed_minutes_this_product += chunk_to_process
                processed_since_inter_reset += chunk_to_process
                processed_since_full_reset += chunk_to_process

            event_triggered = None
            if processed_since_full_reset >= full_gap_min:
                event_triggered = 'full'
            elif processed_since_inter_reset >= inter_gap_min:
                event_triggered = 'intermediate'

            if event_triggered == 'full':
                fw_start = current_time
                fw_end = fw_start + timedelta(minutes=full_wash_dur_min)
                iw_start = fw_start
                iw_end = iw_start + timedelta(minutes=inter_wash_dur_min)
                pause_end = max(fw_end, iw_end)
                _add_segment_with_merge_logic(None, 'WASH', fw_start, fw_end, 'full wash')
                _add_segment_with_merge_logic(None, 'WASH', iw_start, iw_end, 'intermediate wash')
                current_time = pause_end
                processed_since_inter_reset = 0.0
                processed_since_full_reset = 0.0
                continue
            elif event_triggered == 'intermediate':
                iw_start = current_time
                iw_end = iw_start + timedelta(minutes=inter_wash_dur_min)
                _add_segment_with_merge_logic(None, 'WASH', iw_start, iw_end, 'intermediate wash')
                current_time = iw_end
                processed_since_inter_reset = 0.0
                processed_since_full_reset += inter_wash_dur_min
                continue

    return segments, batch_marks

def plot_schedule(segments, batch_marks, chart_title_from_data):
    """Plot horizontal-time Gantt-like chart."""
    product_order = []
    for s in segments:
        if s['product_idx'] is not None:
            if s['product_name'] not in product_order:
                product_order.append(s['product_name'])
    if not product_order:
        product_order = sorted(list(set([bm['product_name'] for bm in batch_marks])))
    product_order.reverse()

    wrapped_product_order = [textwrap.fill(name, width=20) for name in product_order]
    product_to_y = {p: idx for idx, p in enumerate(product_order)}
    lane_height = 1.0

    colors = {
        'production': '#2ca02c',
        'full wash': '#5D005D',
        'intermediate wash': '#7fb3ff',
        'changeover': '#ff7f0e'
    }

    fig = plt.figure(figsize=(16.5, 11.7), dpi=300)
    ax = fig.add_subplot(111)

    def d2n(dt):
        return mdates.date2num(pd.to_datetime(dt))

    full_wash_starts = {s['start'] for s in segments if s['kind'] == 'full wash'}

    for s in segments:
        kind = s['kind']
        if kind == 'intermediate wash' and s['start'] in full_wash_starts:
            continue

        col = colors.get(kind, '#999999')
        x0 = d2n(s['start'])
        x1 = d2n(s['end'])
        width = x1 - x0

        if s['product_idx'] is None:
            y0 = -0.5
            height = len(product_order)
            rect = patches.Rectangle(
                (x0, y0),
                width,
                height,
                facecolor=col, alpha=0.25, edgecolor=None
            )
            ax.add_patch(rect)

            y_label_pos_wash = -0.4
            ax.text(x0, y_label_pos_wash, s['start'].strftime('%H:%M'), va='bottom', ha='left', fontsize=6, color='grey', alpha=0.8, rotation=90)
            ax.text(x1, y_label_pos_wash, s['end'].strftime('%H:%M'), va='bottom', ha='right', fontsize=6, color='grey', alpha=0.8, rotation=90)
        else:
            y_center = product_to_y[s['product_name']]
            y_bottom = y_center - lane_height/2
            y_top = y_center + lane_height/2
            rect = patches.Rectangle(
                (x0, y_bottom),
                width,
                lane_height,
                facecolor=col, edgecolor='black', linewidth=0.2
            )
            ax.add_patch(rect)

            ax.text(x0 + 0.01*width, y_top - 0.05*lane_height, s['start'].strftime('%H:%M'), va='top', ha='left', fontsize=6, color='black', alpha=0.8, rotation=90)
            ax.text(x1 - 0.01*width, y_bottom + 0.05*lane_height, s['end'].strftime('%H:%M'), va='bottom', ha='right', fontsize=6, color='black', alpha=0.8, rotation=90)

    for bm in batch_marks:
        x = d2n(bm['time'])
        y_center = product_to_y[bm['product_name']]
        y_bottom = y_center - lane_height/2
        y_top = y_center + lane_height/2

        ax.plot([x, x], [y_bottom, y_top], color='lightgrey', linewidth=0.8, solid_capstyle='butt', zorder=5)
        label_y_position = y_bottom + lane_height * 0.5
        ax.text(x, label_y_position, bm['label'], va='center', ha='center', fontsize=7, color='black', rotation=90, zorder=6)

    if segments:
        min_date = min(s['start'] for s in segments).floor('D')
        max_date = max(s['end'] for s in segments).ceil('D')
        day_range = pd.date_range(start=min_date, end=max_date + timedelta(days=1), freq='D')

        for day in day_range:
            ax.axvline(x=d2n(day), color='gray', linestyle='--', linewidth=0.7, alpha=0.7)

            if day.weekday() == 5 or day.weekday() == 6:
                rect = patches.Rectangle(
                    (d2n(day), ax.get_ylim()[0]),
                    d2n(day + timedelta(days=1)) - d2n(day),
                    ax.get_ylim()[1] - ax.get_ylim()[0],
                    facecolor='#FFEC8B', alpha=0.3, zorder=0
                )
                ax.add_patch(rect)

    ax.set_ylim(-0.5, len(product_order)-0.5)
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %d %b %H:%M'))

    plt.xticks(rotation=90, ha='center', va='top', rotation_mode='anchor', fontsize=7)
    ax.grid(axis='x', linestyle=':', alpha=0.3)

    ax.set_yticks(range(len(product_order)))
    ax.set_yticklabels(wrapped_product_order, rotation=0, fontsize=9, ha='right')

    ax.set_ylabel('Product (sequence as given)')
    ax.set_xlabel('Time & Day')
    ax.set_title(chart_title_from_data, fontsize=16, fontweight='bold')

    legend_patches = [patches.Patch(color=colors[k], label=k.title()) for k in ['production','full wash','changeover']]
    ax.legend(handles=legend_patches, loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=8, frameon=True)

    sydney_tz = pytz.timezone('Australia/Sydney')
    current_dt_sydney = datetime.now(sydney_tz).strftime('%Y-%m-%d %H:%M %Z%z')
    fig.text(0.02, 0.02, f"Execution Date: {current_dt_sydney}", ha='left', va='bottom', fontsize=10, transform=fig.transFigure)

    fig.subplots_adjust(top=0.9, bottom=0.1)
    
    return fig

# Streamlit App
st.set_page_config(page_title="Production Planner", layout="wide")

st.title("🏭 Production Schedule Planner")
st.markdown("Upload your Excel file to generate a production schedule with wash timing visualization.")

# File uploader
uploaded_file = st.file_uploader("Choose an Excel file", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        # Read Excel file
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        df.dropna(subset=['product name'], inplace=True)
        
        # Extract chart title
        chart_title_from_data = 'Production Schedule'
        if 'title' in df.columns:
            if len(df) > 1 and pd.notna(df.loc[1, 'title']) and str(df.loc[1, 'title']).strip() != '':
                chart_title_from_data = str(df.loc[1, 'title']).strip()
            elif pd.notna(df.loc[0, 'title']) and str(df.loc[0, 'title']).strip() != '':
                chart_title_from_data = str(df.loc[0, 'title']).strip()
        
        # Display data preview
        with st.expander("📊 Preview Input Data"):
            st.dataframe(df)
        
        # Generate schedule button
        if st.button("Generate Schedule", type="primary"):
            with st.spinner("Generating production schedule..."):
                # Build schedule
                segments, batch_marks = schedule_plan(df)
                
                # Plot schedule
                fig = plot_schedule(segments, batch_marks, chart_title_from_data)
                
                # Display plot
                st.pyplot(fig)
                
                # Download button
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
                buf.seek(0)
                
                st.download_button(
                    label="📥 Download Schedule (PNG)",
                    data=buf,
                    file_name="production_planner_horizontal.png",
                    mime="image/png"
                )
                
                plt.close(fig)
                
                st.success("✅ Schedule generated successfully!")
                
    except Exception as e:
        st.error(f"❌ Error processing file: {str(e)}")
        st.exception(e)
else:
    st.info("👆 Please upload an Excel file to get started.")
    
    # Instructions
    with st.expander("ℹ️ Required Excel Columns"):
        st.markdown("""
        Your Excel file must contain the following columns:
        - **Product Name**: Name of the product
        - **Quantity Liters**: Total quantity to process
        - **Process Speed Per Hour**: Processing speed (liters/hour)
        - **Qty of Batch**: Batch size in liters
        - **Date From**: Start date/time
        - **First Wash Time**: Time for first full wash
        - **Gap** or **Full Gap**: Minutes between full washes
        - **Intermediate Gap**: Minutes between intermediate washes (optional, defaults to 1440)
        - **Intermediate Wash Duration**: Duration of intermediate wash (minutes)
        - **Duration**: Duration of full wash (minutes)
        - **Line Efficiency**: Efficiency factor (0-1, defaults to 1.0)
        - **Changeover Duration** or **Change Over**: Changeover time (optional)
        - **Additional Wash**: 'yes' to trigger additional wash (optional)
        - **Title**: Chart title (optional)
        """)