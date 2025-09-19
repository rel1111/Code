import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import streamlit as st
import io

def generate_timeline(df):
    """
    Processes the production plan data and generates a timeline.

    Args:
        df (pd.DataFrame): The DataFrame containing the production plan data.

    Returns:
        matplotlib.figure.Figure: The generated timeline figure.
    """
    # Define colors for each task
    colors = {
        'processing': 'darkgreen',
        'wash': 'purple',
        'changeover': 'darkorange'
    }

    tasks = []

    # Get the start date and time
    try:
        start_time_of_week = pd.to_datetime(df.loc[0, 'Date from'])
    except Exception as e:
        st.error(f"❌ Error parsing 'Date from' column: {e}. Please ensure it's in a valid date/time format.")
        return None

    current_time = start_time_of_week

    # Wash duration & gap
    try:
        wash_duration_mins = int(df.loc[0, 'Duration'])
        wash_gap_mins = int(df.loc[0, 'Gap'])
        wash_duration = timedelta(minutes=wash_duration_mins)
        gap_duration = timedelta(minutes=wash_gap_mins)
    except KeyError as e:
        st.warning(f"⚠️ Missing wash column: {e}. Wash cycle will not be scheduled.")
        wash_duration = timedelta(0)
        gap_duration = timedelta(0)
    except ValueError as e:
        st.warning(f"⚠️ Error converting wash duration/gap: {e}. Wash cycle will not be scheduled.")
        wash_duration = timedelta(0)
        gap_duration = timedelta(0)
    except Exception as e:
        st.warning(f"⚠️ Error reading wash time: {e}. Wash cycle will not be scheduled.")
        wash_duration = timedelta(0)
        gap_duration = timedelta(0)

    # Optional: First Wash Time
    first_wash_time = None
    try:
        first_wash_time = pd.to_datetime(df.loc[0, 'First Wash Time'])
        last_wash_end_time = first_wash_time
    except KeyError:
        st.info("ℹ️ 'First Wash Time' column not found. Scheduling based on 'Date from' + 'Gap'.")
        last_wash_end_time = start_time_of_week
    except Exception as e:
        st.warning(f"⚠️ Error reading 'First Wash Time': {e}. Scheduling based on 'Date from' + 'Gap'.")
        last_wash_end_time = start_time_of_week

    if first_wash_time and wash_duration > timedelta(0):
        tasks.append({
            'start': first_wash_time,
            'end': first_wash_time + wash_duration,
            'duration_hours': wash_duration.total_seconds() / 3600,
            'task': 'wash',
            'product': 'Scheduled Wash',
            'order': -2
        })
        last_wash_end_time = first_wash_time + wash_duration

    # Iterate through products
    for i, row in df.iterrows():
        product_name = row['product name']
        quantity_liters = row['quantity liters']
        process_speed = row['process speed per hour']
        line_efficiency = row['line efficiency']
        change_over_mins = row['Change Over']

        # Changeover
        if i > 0:
            change_over_duration = timedelta(minutes=change_over_mins)
            changeover_end_time = current_time + change_over_duration

            # Schedule washes during changeover
            next_wash_start_time = last_wash_end_time + gap_duration
            scheduled_washes_in_changeover = []
            while next_wash_start_time < changeover_end_time:
                wash_end_time = next_wash_start_time + wash_duration
                scheduled_washes_in_changeover.append({'start': next_wash_start_time, 'end': wash_end_time})
                last_wash_end_time = wash_end_time
                next_wash_start_time = last_wash_end_time + gap_duration

            overlaps = any(
                max(current_time, wash['start']) < min(changeover_end_time, wash['end'])
                for wash in scheduled_washes_in_changeover
            )

            if overlaps:
                overlapping_washes = [wash for wash in scheduled_washes_in_changeover if max(current_time, wash['start']) < min(changeover_end_time, wash['end'])]
                if overlapping_washes:
                    current_time = max(wash['end'] for wash in overlapping_washes)
                for wash in scheduled_washes_in_changeover:
                    tasks.append({
                        'start': wash['start'],
                        'end': wash['end'],
                        'duration_hours': (wash['end'] - wash['start']).total_seconds() / 3600,
                        'task': 'wash',
                        'product': 'Scheduled Wash',
                        'order': -1
                    })
            else:
                tasks.append({
                    'start': current_time,
                    'end': changeover_end_time,
                    'duration_hours': change_over_mins / 60,
                    'task': 'changeover',
                    'product': product_name,
                    'order': i
                })
                current_time = changeover_end_time

        # Processing
        effective_speed = process_speed * line_efficiency
        total_processing_hours = quantity_liters / effective_speed
        processing_end_time = current_time + timedelta(hours=total_processing_hours)

        # Washes in processing
        total_wash_overlap_duration = timedelta(0)
        next_wash_start_time = last_wash_end_time + gap_duration
        while next_wash_start_time < processing_end_time + total_wash_overlap_duration:
            wash_end_time = next_wash_start_time + wash_duration
            overlap_start = max(current_time, next_wash_start_time)
            overlap_end = min(processing_end_time + total_wash_overlap_duration, wash_end_time)

            if overlap_start < overlap_end:
                total_wash_overlap_duration += (overlap_end - overlap_start)
                if not (first_wash_time and next_wash_start_time == first_wash_time):
                    tasks.append({
                        'start': next_wash_start_time,
                        'end': wash_end_time,
                        'duration_hours': wash_duration.total_seconds() / 3600,
                        'task': 'wash',
                        'product': 'Scheduled Wash',
                        'order': -1
                    })
                last_wash_end_time = wash_end_time
                next_wash_start_time = last_wash_end_time + gap_duration
            else:
                break

        extended_processing_end_time = processing_end_time + total_wash_overlap_duration

        # Processing segments
        segment_start_time = current_time
        scheduled_wash_intervals = [
            (wash['start'], wash['end']) for wash in tasks
            if wash['task'] == 'wash' and max(current_time, wash['start']) < min(processing_end_time, wash['end'])
        ]
        scheduled_wash_intervals.sort()

        for wash_start, wash_end in scheduled_wash_intervals:
            if segment_start_time < wash_start:
                tasks.append({
                    'start': segment_start_time,
                    'end': wash_start,
                    'duration_hours': (wash_start - segment_start_time).total_seconds() / 3600,
                    'task': 'processing',
                    'product': product_name,
                    'order': i
                })
            segment_start_time = max(segment_start_time, wash_end)

        if segment_start_time < extended_processing_end_time:
            tasks.append({
                'start': segment_start_time,
                'end': extended_processing_end_time,
                'duration_hours': (extended_processing_end_time - segment_start_time).total_seconds() / 3600,
                'task': 'processing',
                'product': product_name,
                'order': i
            })

        current_time = extended_processing_end_time

    # Plot
    fig, ax = plt.subplots(figsize=(18, 8))
    ax.set_facecolor('white')

    y_pos = 0
    product_y_positions = {}
    product_order = []

    tasks_df = pd.DataFrame(tasks).sort_values(by='order')
    unique_products_ordered = ['Scheduled Wash'] + [p for p in tasks_df['product'].unique() if p != 'Scheduled Wash']

    for product_name in unique_products_ordered:
        group = tasks_df[tasks_df['product'] == product_name].sort_values(by='start')
        product_y_positions[product_name] = y_pos
        product_order.append(product_name)
        for _, task in group.iterrows():
            ax.broken_barh(
                [(mdates.date2num(task['start']), (task['end'] - task['start']).total_seconds() / (24*3600))],
                (y_pos - 0.4, 0.8),
                facecolors=colors[task['task']], edgecolor='black'
            )
        y_pos += 1

    ax.set_yticks(list(product_y_positions.values()))
    ax.set_yticklabels(product_order)
    ax.set_xlabel("⏰ Time")
    ax.set_title("📊 Weekly Production Plan Timeline")
    ax.grid(False)  # we'll specify grids explicitly
    ax.invert_yaxis()

    # X-axis formatting
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %m-%d'))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    ax.xaxis.set_minor_formatter(mdates.DateFormatter('%H:%M'))

    # Add alternating day shading and stronger day dividers
    if not tasks_df.empty:
        first_date = tasks_df['start'].min().floor('D')
        last_date = tasks_df['end'].max().ceil('D')
        delta_days = (last_date - first_date).days + 1
        for day in range(delta_days):
            day_start = first_date + timedelta(days=day)
            # subtle alternating background to help visually separate days
            if day % 2 == 0:
                ax.axvspan(day_start, day_start + timedelta(days=1), facecolor='lightgray', alpha=0.12, zorder=0)
            # stronger vertical day divider
            ax.axvline(day_start, color='black', linestyle='--', linewidth=1.0, alpha=0.8, zorder=2)

    # Clearer grid lines
    ax.grid(True, which='major', color='black', linestyle='--', linewidth=0.9, alpha=0.5)
    ax.grid(True, which='minor', color='lightgray', linestyle=':', linewidth=0.6, alpha=0.9)

    # Rotate date labels for readability
    plt.xticks(rotation=45, ha='right', va='top')
    plt.setp(ax.get_xminorticklabels(), rotation=45, ha='right', va='top')

    handles = [plt.Rectangle((0, 0), 1, 1, fc=colors[t]) for t in colors]
    ax.legend(handles, colors.keys(), loc='upper right')

    plt.tight_layout()
    return fig

def main():
    st.set_page_config(page_title="Production Plan Timeline", layout="wide")
    
    st.title("📊 Production Plan Timeline Generator")
    st.write("Upload your production plan file (CSV or Excel) to generate a timeline visualization.")
    
    uploaded_file = st.file_uploader(
        "📂 Choose a file",
        type=['csv', 'xlsx', 'xls'],
        help="Upload a CSV or Excel file containing your production plan data."
    )
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success(f"✅ File uploaded successfully: {uploaded_file.name}")
            
            st.subheader("📋 Data Preview")
            st.dataframe(df.head())
            
            required_columns = ['product name', 'quantity liters', 'process speed per hour', 
                              'line efficiency', 'Change Over', 'Date from', 'Duration', 'Gap']
            optional_columns = ['First Wash Time']
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"❌ Missing required columns: {', '.join(missing_columns)}")
                st.write("**Required columns:**")
                for col in required_columns:
                    status = "✅" if col in df.columns else "❌"
                    st.write(f"{status} {col}")
                st.write("**Optional columns:**")
                for col in optional_columns:
                    status = "✅" if col in df.columns else "⚪"
                    st.write(f"{status} {col}")
            else:
                st.success("✅ All required columns found!")
                
                for col in optional_columns:
                    if col in df.columns:
                        st.info(f"Optional column '{col}' found - will be used for scheduling.")
                    else:
                        st.info(f"Optional column '{col}' not found - scheduling will default to 'Date from' + 'Gap'.")
                
                if st.button("🚀 Generate Timeline", type="primary"):
                    with st.spinner("⏳ Generating timeline..."):
                        fig = generate_timeline(df)
                        
                        if fig:
                            st.subheader("📈 Production Timeline")
                            st.pyplot(fig)
                            
                            buf = io.BytesIO()
                            fig.savefig(buf, format='png', bbox_inches='tight', dpi=300)
                            buf.seek(0)
                            
                            st.download_button(
                                label="📥 Download Timeline as PNG",
                                data=buf.getvalue(),
                                file_name="production_timeline.png",
                                mime="image/png"
                            )
                        else:
                            st.error("❌ Failed to generate timeline. Please check your data format.")
        
        except Exception as e:
            st.error(f"❌ Error reading file: {str(e)}")
    else:
        st.info("👆 Please upload a file to get started.")
        
        with st.expander("📄 Expected File Format"):
            st.write("Your file should contain the following columns:")
            st.write("**Required columns:**")
            required_cols = ['product name', 'quantity liters', 'process speed per hour',
                           'line efficiency', 'Change Over', 'Date from', 'Duration', 'Gap']
            for i, col in enumerate(required_cols, 1):
                st.write(f"{i}. **{col}**")
            
            st.write("**Optional columns:**")
            st.write("9. **First Wash Time** - If provided, will schedule the first wash at this specific time")

if __name__ == "__main__":
    main()
