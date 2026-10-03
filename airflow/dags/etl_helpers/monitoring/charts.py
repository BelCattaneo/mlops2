"""
Chart Generation Functions

Functions for creating visualizations for monitoring and logging.
"""

import logging
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)


def create_bar_chart(
    values: List[float],
    labels: List[str],
    title: str,
    xlabel: str,
    ylabel: str,
    horizontal: bool = False,
    figsize: Tuple[int, int] = (10, 6),
) -> plt.Figure:
    """
    Create a bar chart.

    Args:
        values: Bar values
        labels: Bar labels
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        horizontal: Whether to create horizontal bars
        figsize: Figure size tuple

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    if horizontal:
        ax.barh(range(len(values)), values)
        ax.set_yticks(range(len(values)))
        ax.set_yticklabels(labels)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.invert_yaxis()
    else:
        ax.bar(range(len(values)), values)
        ax.set_xticks(range(len(values)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

    ax.set_title(title)
    ax.grid(axis="y" if not horizontal else "x", alpha=0.3)
    plt.tight_layout()
    return fig


def create_comparison_bar_chart(
    values1: List[float],
    values2: List[float],
    labels: List[str],
    label1: str,
    label2: str,
    title: str,
    xlabel: str,
    ylabel: str,
    figsize: Tuple[int, int] = (10, 6),
) -> plt.Figure:
    """
    Create a side-by-side comparison bar chart.

    Args:
        values1: First set of bar values
        values2: Second set of bar values
        labels: Bar labels
        label1: Legend label for first set
        label2: Legend label for second set
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        figsize: Figure size tuple

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    x = np.arange(len(labels))
    width = 0.35

    ax.bar(x - width / 2, values1, width, label=label1, alpha=0.8)
    ax.bar(x + width / 2, values2, width, label=label2, alpha=0.8)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    return fig


def create_raw_data_overview_chart(df: pd.DataFrame) -> plt.Figure:
    """
    Generate overview charts for raw data.

    Args:
        df: Raw crime data DataFrame

    Returns:
        Matplotlib figure with 4 subplots
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Chart 1: Top 10 districts
    if "district" in df.columns:
        district_counts = df["district"].value_counts().head(10)
        axes[0, 0].barh(range(len(district_counts)), district_counts.values)
        axes[0, 0].set_yticks(range(len(district_counts)))
        axes[0, 0].set_yticklabels(district_counts.index)
        axes[0, 0].set_xlabel("Crime Count")
        axes[0, 0].set_title("Top 10 Districts by Crime Count")
        axes[0, 0].invert_yaxis()
        axes[0, 0].grid(axis="x", alpha=0.3)

    # Chart 2: Daily crime trend
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        daily_counts = df.groupby(df["date"].dt.date).size()
        axes[0, 1].plot(daily_counts.index, daily_counts.values)
        axes[0, 1].set_xlabel("Date")
        axes[0, 1].set_ylabel("Crime Count")
        axes[0, 1].set_title("Daily Crime Trend")
        axes[0, 1].tick_params(axis="x", rotation=45)
        axes[0, 1].grid(axis="y", alpha=0.3)

    # Chart 3: Arrest distribution
    if "arrest" in df.columns:
        arrest_counts = df["arrest"].value_counts()
        axes[1, 0].pie(
            arrest_counts.values,
            labels=["No Arrest", "Arrest"],
            autopct="%1.1f%%",
            startangle=90,
        )
        axes[1, 0].set_title("Arrest vs No Arrest Distribution")

    # Chart 4: Top 10 crime types
    if "primary_type" in df.columns:
        type_counts = df["primary_type"].value_counts().head(10)
        axes[1, 1].barh(range(len(type_counts)), type_counts.values)
        axes[1, 1].set_yticks(range(len(type_counts)))
        axes[1, 1].set_yticklabels(type_counts.index)
        axes[1, 1].set_xlabel("Crime Count")
        axes[1, 1].set_title("Top 10 Crime Types")
        axes[1, 1].invert_yaxis()
        axes[1, 1].grid(axis="x", alpha=0.3)

    plt.tight_layout()
    return fig


def create_correlation_heatmap(
    df: pd.DataFrame,
    title: str = "Feature Correlation Heatmap",
) -> Optional[plt.Figure]:
    """
    Generate correlation heatmap of numeric features.

    Args:
        df: DataFrame with numeric columns
        title: Chart title

    Returns:
        Matplotlib figure or None if not enough numeric features
    """
    numeric_df = df.select_dtypes(include=[np.number])

    if len(numeric_df.columns) < 2:
        logger.warning("Not enough numeric features for correlation heatmap")
        return None

    fig, ax = plt.subplots(figsize=(12, 10))

    corr_matrix = numeric_df.corr()
    sns.heatmap(
        corr_matrix,
        annot=False,
        cmap="coolwarm",
        center=0,
        vmin=-1,
        vmax=1,
        ax=ax,
        cbar_kws={"label": "Correlation"},
    )
    ax.set_title(title)

    plt.tight_layout()
    return fig


def create_pipeline_flow_chart(
    raw_count: int,
    enriched_count: int,
    train_count: int,
    test_count: int,
    balanced_count: int,
    final_train_count: int,
    final_test_count: int,
) -> plt.Figure:
    """
    Generate pipeline data flow chart showing record counts at each stage.

    Args:
        raw_count: Number of raw records
        enriched_count: Number of enriched records
        train_count: Number of training records after split
        test_count: Number of test records after split
        balanced_count: Number of records after balancing
        final_train_count: Number of final training records
        final_test_count: Number of final test records

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=(14, 8))

    stages = [
        "Raw\nData",
        "Enriched\nData",
        "Train\nSplit",
        "Balanced\nTrain",
        "Final\nTrain",
        "Final\nTest",
    ]
    counts = [
        raw_count,
        enriched_count,
        train_count,
        balanced_count,
        final_train_count,
        final_test_count,
    ]

    x_positions = [0, 1, 2.5, 3.5, 5, 5]
    colors = ["#3498db", "#2ecc71", "#f39c12", "#e74c3c", "#9b59b6", "#1abc9c"]

    bars = ax.bar(x_positions, counts, color=colors, alpha=0.7, width=0.6)

    for bar, count in zip(bars, counts):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{count:,}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xticks(x_positions)
    ax.set_xticklabels(stages, fontsize=11)

    retention_texts = [
        f"{(enriched_count / raw_count * 100):.1f}%" if raw_count > 0 else "N/A",
        f"{(train_count / enriched_count * 100):.1f}%" if enriched_count > 0 else "N/A",
        f"{(balanced_count / train_count * 100):.1f}%" if train_count > 0 else "N/A",
        f"{(final_train_count / balanced_count * 100):.1f}%"
        if balanced_count > 0
        else "N/A",
    ]

    arrow_positions = [(0, 1), (1, 2.5), (2.5, 3.5), (3.5, 5)]

    for (start, end), text in zip(arrow_positions, retention_texts):
        mid_x = (start + end) / 2
        mid_y = max(counts) * 0.5
        ax.annotate(
            text,
            xy=(mid_x, mid_y),
            fontsize=9,
            ha="center",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
        )

    ax.annotate(
        f"Test: {test_count:,}\n({(test_count / enriched_count * 100):.1f}%)"
        if enriched_count > 0
        else f"Test: {test_count:,}",
        xy=(2.5, train_count),
        xytext=(1.5, max(counts) * 0.3),
        fontsize=9,
        ha="center",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="yellow", alpha=0.3),
        arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.3", lw=1.5),
    )

    ax.set_ylabel("Record Count", fontsize=12, fontweight="bold")
    ax.set_title(
        "ETL Pipeline Data Flow - Record Count by Stage", fontsize=14, fontweight="bold"
    )
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_ylim(0, max(counts) * 1.15)

    plt.tight_layout()
    return fig
