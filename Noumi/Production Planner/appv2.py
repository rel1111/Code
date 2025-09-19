import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

def generate_timeline(schedule):
    fig, ax = plt.subplots(figsize=(18, 6))

    colors = {
        "processing": "darkgreen",
        "wash": "purple",
        "changeover": "orange",
    }

    y_labels = []
    y_ticks = []
    y_pos = 0

    for group_name, group in schedule.groupby("product"):
        y_labels.append(group_name)
        y_ticks.append(y_pos)

        for _, task in group.iterrows():
            start_num = mdates.date2num(task["start"])
            end_num = mdates.date2num(task["end"])
            duration = end_num - start_num

            # draw the bar
            ax.broken_barh(
                [(start_num, duration)],
                (y_pos - 0.4, 0.8),
                facecolors=colors[task["task"]],
                edgecolor="black",
            )

            # add label with start-end time
            ax.text(
                start_num + duration / 2,
                y_pos,
                f"{task['start'].strftime('%H:%M')}–{task['end'].strftime('%H:%M')}",
                ha="center",
                va="center",
                fontsize=8,
                color="white",
                fontweight="bold",
            )

        y_pos += 1

    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels)
    ax.set_xlabel("Time")
    ax.set_title("Weekly Production Plan Timeline")

    # Major ticks = 1 day, Minor ticks = 6 hours
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d"))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    ax.xaxis.set_minor_formatter(mdates.DateFormatter("%H:%M"))

    # Rotate labels for readability
    plt.setp(ax.get_xticklabels(which="both"), rotation=45, ha="right")

    # Grid styling
    ax.grid(True, which="major", color="black", linestyle="--", linewidth=1.2, alpha=0.8)
    ax.grid(True, which="minor", color="lightgray", linestyle=":", linewidth=0.7, alpha=0.7)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=colors["processing"], label="processing"),
        Patch(facecolor=colors["wash"], label="wash"),
        Patch(facecolor=colors["changeover"], label="changeover"),
    ]
    ax.legend(handles=legend_elements, loc="upper right")

    plt.tight_layout()
    plt.show()


# Example dummy schedule
schedule = pd.DataFrame([
    {"product": "Product A", "task": "processing", "start": pd.Timestamp("2025-09-19 20:00"), "end": pd.Timestamp("2025-09-20 06:00")},
    {"product": "Product B", "task": "changeover", "start": pd.Timestamp("2025-09-20 06:00"), "end": pd.Timestamp("2025-09-20 06:45")},
    {"product": "Product B", "task": "processing", "start": pd.Timestamp("2025-09-20 06:45"), "end": pd.Timestamp("2025-09-20 13:45")},
    {"product": "Scheduled Wash", "task": "wash", "start": pd.Timestamp("2025-09-19 07:30"), "end": pd.Timestamp("2025-09-19 12:30")},
])

generate_timeline(schedule)
