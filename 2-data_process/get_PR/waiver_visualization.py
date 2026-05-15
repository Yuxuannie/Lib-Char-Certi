#!/usr/bin/env python3

import os
import pandas as pd
import numpy as np
import logging

"""
Unified Waiver System Visualization Module

Creates enhanced visualizations showing 4-bar comparison for the unified waiver system:
- Base PR (blue)
- PR + Waiver1 (green)
- PR Optimistic Only (orange)
- PR + Both Waivers (purple)

Also generates stacked bar charts showing optimistic vs pessimistic error distribution.
"""

def create_waiver_comparison_visualization(results, root_path, analysis_type='sigma'):
    """
    Create visualization showing 4-bar comparison of pass rates with waiver system

    Args:
        results: Dictionary with (file_name, type) keys and waiver data as values
        root_path: Root directory to save visualizations
        analysis_type: 'sigma' or 'moments' for appropriate labeling

    Returns:
        list: Paths to generated visualization files
    """
    logging.info(f"Creating {analysis_type} waiver comparison visualizations with 4-bar comparison")

    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator
        import numpy as np

        # Set style for better aesthetics
        plt.style.use('seaborn-v0_8-whitegrid')

        # Color scheme for 4 pass rates
        waiver_colors = {
            'base_pr': '#3498db',              # Blue - Base pass rate
            'pr_with_waiver1': '#2ecc71',      # Green - Base + CI enlargement
            'pr_optimistic_only': '#f39c12',   # Orange - Optimistic only
            'pr_with_both_waivers': '#9b59b6'  # Purple - Both waivers
        }

        # Set font properties
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
        plt.rcParams['font.size'] = 12
        plt.rcParams['axes.titlesize'] = 16
        plt.rcParams['axes.labelsize'] = 14

        # Extract corner name function
        def extract_corner_from_filename(file_name):
            """Extract full corner name from filename"""
            base_name = file_name.replace('.rpt', '').replace('MC_', '').replace('fmc_', '')
            import re
            corner_pattern = r'(ssg[ng][pg]_[0-9]p[0-9]+v_[mn][0-9]+c)'
            match = re.search(corner_pattern, base_name)
            if match:
                return match.group(1)
            return base_name.split('_')[0] if base_name else 'unknown'

        # Organize data by corner and type
        data_by_corner_type = {}
        for (file_name, type_name), param_data in results.items():
            corner = extract_corner_from_filename(file_name)
            logging.info(f"Extracted corner '{corner}' from file '{file_name}'")

            if corner not in data_by_corner_type:
                data_by_corner_type[corner] = {}
            data_by_corner_type[corner][type_name] = param_data

        visualization_files = []

        # Determine parameters based on analysis type
        if analysis_type == 'sigma':
            # For sigma: Early_Sigma and Late_Sigma
            param_groups = {
                'Early_Sigma': ['delay', 'slew'],
                'Late_Sigma': ['delay', 'slew', 'hold']
            }
        else:  # moments
            # For moments: Meanshift, Std, Skew
            param_groups = {
                'Meanshift': ['delay', 'slew'],
                'Std': ['delay', 'slew'],
                'Skew': ['delay', 'slew']
            }

        # Create visualization for each parameter
        for param_name, applicable_types in param_groups.items():
            logging.info(f"Creating {analysis_type} waiver visualization for: {param_name}")

            # Collect data for this parameter
            plot_data = {}  # Will hold arrays for each pass rate type
            labels = []
            type_groups = []

            # Initialize data arrays for 4 pass rate types
            base_pr_data = []
            pr_with_waiver1_data = []
            pr_optimistic_only_data = []
            pr_with_both_waivers_data = []

            # Collect data for each type-corner combination
            for type_name in sorted(applicable_types):
                for corner in sorted(data_by_corner_type.keys()):
                    if (type_name in data_by_corner_type[corner] and
                        param_name in data_by_corner_type[corner][type_name]):

                        stats = data_by_corner_type[corner][type_name][param_name]

                        # Extract 4 pass rates
                        base_pr = stats['base_pr']
                        pr_with_waiver1 = stats['pr_with_waiver1']
                        pr_optimistic_only = stats['pr_optimistic_only']
                        pr_with_both_waivers = stats['pr_with_both_waivers']

                        base_pr_data.append(base_pr)
                        pr_with_waiver1_data.append(pr_with_waiver1)
                        pr_optimistic_only_data.append(pr_optimistic_only)
                        pr_with_both_waivers_data.append(pr_with_both_waivers)

                        # Create clean labels
                        corner_short = corner.replace('ssgnp_', '').replace('ssgng_', '').replace('_m40c', '')
                        labels.append(f"{type_name.upper()}\n{corner_short}")
                        type_groups.append(type_name)

            if not base_pr_data:
                logging.warning(f"No data found for {param_name}")
                continue

            # Create figure
            fig, ax = plt.subplots(figsize=(max(18, len(labels) * 1.5), 12))

            x = np.arange(len(labels))
            width = 0.2  # Width of each bar
            spacing = 0.8  # Spacing between groups

            # Create 4 bars for each corner/type combination
            bars1 = ax.bar(x - 1.5*width, base_pr_data, width,
                          color=waiver_colors['base_pr'], alpha=0.9,
                          label='Base PR', edgecolor='black', linewidth=1)

            bars2 = ax.bar(x - 0.5*width, pr_with_waiver1_data, width,
                          color=waiver_colors['pr_with_waiver1'], alpha=0.9,
                          label='PR + Waiver1 (CI enlarged)', edgecolor='black', linewidth=1)

            bars3 = ax.bar(x + 0.5*width, pr_optimistic_only_data, width,
                          color=waiver_colors['pr_optimistic_only'], alpha=0.9,
                          label='PR Optimistic Only', edgecolor='black', linewidth=1)

            bars4 = ax.bar(x + 1.5*width, pr_with_both_waivers_data, width,
                          color=waiver_colors['pr_with_both_waivers'], alpha=0.9,
                          label='PR + Both Waivers', edgecolor='black', linewidth=1)

            # Add value labels on bars > 5%
            for bars, data in [(bars1, base_pr_data), (bars2, pr_with_waiver1_data),
                              (bars3, pr_optimistic_only_data), (bars4, pr_with_both_waivers_data)]:
                for bar, value in zip(bars, data):
                    if value > 5:  # Only label significant values
                        height = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                               f'{value:.1f}%', ha='center', va='bottom',
                               fontweight='bold', fontsize=10)

            # Add type separators with alternating background colors
            current_type = None
            type_start = 0
            for i, group_type in enumerate(type_groups):
                if current_type != group_type:
                    if current_type is not None:
                        # Add background color for previous type group
                        if applicable_types.index(current_type) % 2 == 0:
                            ax.axvspan(type_start - 0.5, i - 0.5, alpha=0.05, color='blue', zorder=0)
                        # Add vertical separator
                        ax.axvline(x=i - 0.5, color='black', linestyle='-', alpha=0.3, linewidth=2)
                    current_type = group_type
                    type_start = i

            # Add background for last type group
            if current_type and applicable_types.index(current_type) % 2 == 0:
                ax.axvspan(type_start - 0.5, len(labels) - 0.5, alpha=0.05, color='blue', zorder=0)

            # Add horizontal line at the pass threshold
            ax.axhline(y=95, linestyle='--', color='red', alpha=0.8, linewidth=2)
            ax.text(len(labels) * 0.02, 97, 'Target: 95%', ha='left', va='bottom',
                   fontsize=12, fontweight='bold', color='red',
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))

            # Add type labels at the top
            current_type = None
            type_start = 0
            type_positions = []
            type_names = []

            for i, group_type in enumerate(type_groups):
                if current_type != group_type:
                    if current_type is not None:
                        # Calculate center position for previous type
                        center_pos = (type_start + i - 1) / 2
                        type_positions.append(center_pos)
                        type_names.append(current_type.upper())
                    current_type = group_type
                    type_start = i

            # Add the last type
            if current_type:
                center_pos = (type_start + len(labels) - 1) / 2
                type_positions.append(center_pos)
                type_names.append(current_type.upper())

            # Add type labels with background
            max_y = max(max(base_pr_data), max(pr_with_waiver1_data),
                       max(pr_optimistic_only_data), max(pr_with_both_waivers_data))
            for pos, name in zip(type_positions, type_names):
                ax.text(pos, max_y + 12, name, ha='center', va='center',
                       fontweight='bold', fontsize=14, color='navy',
                       bbox=dict(boxstyle="round,pad=0.5", facecolor='lightblue', alpha=0.8))

            # Set title and labels
            ax.set_title(f'{analysis_type.title()} {param_name.replace("_", " ")} - Waiver System Analysis (4 Pass Rates)\n' +
                        f'Grouped by Type → Corner | Target: 95% Pass Rate',
                        pad=40, fontweight='bold', fontsize=18)
            ax.set_ylabel('Pass Rate (%)', fontweight='bold')
            ax.set_ylim(0, max_y + 20)  # Give space for type labels

            # Set x-axis labels
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=11)

            # Ensure only integer y-ticks
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))

            # Add gridlines for better readability
            ax.grid(True, axis='y', linestyle='--', alpha=0.4)
            ax.set_axisbelow(True)

            # Set background color
            ax.set_facecolor('#f9f9f9')

            # Add legend with better positioning
            legend = ax.legend(loc='center right', fontsize=12, title='Pass Rate Types',
                             title_fontsize=13, bbox_to_anchor=(0.99, 0.7),
                             framealpha=0.95, edgecolor='black')
            legend.get_title().set_fontweight('bold')

            # Adjust layout
            plt.tight_layout()

            # Save visualization
            param_vis_file = os.path.join(root_path, f"{analysis_type}_{param_name.lower()}_waiver_analysis.png")
            plt.savefig(param_vis_file, dpi=300, bbox_inches='tight', facecolor='white')
            logging.info(f"{analysis_type.title()} {param_name} waiver visualization saved to: {param_vis_file}")
            visualization_files.append(param_vis_file)

            plt.close(fig)

        return visualization_files

    except ImportError as e:
        logging.error(f"Could not create waiver visualization: {str(e)}")
        logging.info("Please install matplotlib to enable visualizations")
        return None
    except Exception as e:
        logging.error(f"Error creating waiver visualization", exc_info=True)
        return None

def create_optimistic_pessimistic_distribution_chart(results, root_path, analysis_type='sigma'):
    """
    Create stacked bar chart showing optimistic vs pessimistic error distribution

    Args:
        results: Dictionary with waiver analysis results
        root_path: Root directory to save visualizations
        analysis_type: 'sigma' or 'moments' for appropriate labeling

    Returns:
        str: Path to generated chart
    """
    logging.info(f"Creating {analysis_type} optimistic vs pessimistic distribution chart")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np

        # Set style
        plt.style.use('seaborn-v0_8-whitegrid')

        # Color scheme
        colors = {
            'optimistic': '#2ecc71',   # Green
            'pessimistic': '#e74c3c'   # Red
        }

        # Extract corner name function
        def extract_corner_from_filename(file_name):
            base_name = file_name.replace('.rpt', '').replace('MC_', '').replace('fmc_', '')
            import re
            corner_pattern = r'(ssg[ng][pg]_[0-9]p[0-9]+v_[mn][0-9]+c)'
            match = re.search(corner_pattern, base_name)
            if match:
                return match.group(1)
            return base_name.split('_')[0] if base_name else 'unknown'

        # Collect data for chart
        labels = []
        optimistic_data = []
        pessimistic_data = []

        for (file_name, type_name), param_data in results.items():
            corner = extract_corner_from_filename(file_name)
            corner_short = corner.replace('ssgnp_', '').replace('ssgng_', '').replace('_m40c', '')

            # Average across all parameters for this corner/type
            total_optimistic = 0
            total_pessimistic = 0
            total_arcs = 0
            param_count = 0

            for param, stats in param_data.items():
                total_optimistic += stats['optimistic_errors']
                total_pessimistic += stats['pessimistic_errors']
                total_arcs += stats['total_arcs']
                param_count += 1

            if param_count > 0:
                # Average percentages
                optimistic_pct = (total_optimistic / total_arcs) * 100 if total_arcs > 0 else 0
                pessimistic_pct = (total_pessimistic / total_arcs) * 100 if total_arcs > 0 else 0

                labels.append(f"{type_name.upper()}\n{corner_short}")
                optimistic_data.append(optimistic_pct)
                pessimistic_data.append(pessimistic_pct)

        if not labels:
            logging.warning("No data for optimistic/pessimistic distribution chart")
            return None

        # Create chart
        fig, ax = plt.subplots(figsize=(max(12, len(labels) * 0.8), 8))

        x = np.arange(len(labels))
        width = 0.6

        # Create stacked bars
        bars1 = ax.bar(x, optimistic_data, width, color=colors['optimistic'],
                      alpha=0.8, label='Optimistic Errors (Lib < MC)')
        bars2 = ax.bar(x, pessimistic_data, width, bottom=optimistic_data,
                      color=colors['pessimistic'], alpha=0.8,
                      label='Pessimistic Errors (Lib ≥ MC)')

        # Add percentage labels
        for i, (opt, pess) in enumerate(zip(optimistic_data, pessimistic_data)):
            if opt > 5:  # Only show significant percentages
                ax.text(i, opt/2, f'{opt:.1f}%', ha='center', va='center',
                       fontweight='bold', color='white', fontsize=10)
            if pess > 5:
                ax.text(i, opt + pess/2, f'{pess:.1f}%', ha='center', va='center',
                       fontweight='bold', color='white', fontsize=10)

        # Customize chart
        ax.set_title(f'{analysis_type.title()} Error Direction Distribution\n' +
                    f'Optimistic vs Pessimistic Errors by Corner and Type',
                    fontweight='bold', fontsize=16, pad=20)
        ax.set_ylabel('Percentage of Total Errors (%)', fontweight='bold')
        ax.set_xlabel('Corner and Type', fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha='right')

        ax.set_ylim(0, 105)
        ax.legend(fontsize=12, loc='upper right')

        # Add grid
        ax.grid(True, axis='y', alpha=0.3, linestyle=':')
        ax.set_axisbelow(True)

        plt.tight_layout()

        # Save chart
        chart_file = os.path.join(root_path, f"{analysis_type}_error_distribution_chart.png")
        plt.savefig(chart_file, dpi=300, bbox_inches='tight', facecolor='white')
        logging.info(f"{analysis_type.title()} error distribution chart saved to: {chart_file}")

        plt.close(fig)
        return chart_file

    except Exception as e:
        logging.error(f"Error creating error distribution chart", exc_info=True)
        return None

def generate_combined_waiver_analysis(sigma_results, moments_results, root_path):
    """
    Generate combined waiver analysis comparing sigma and moments results

    Args:
        sigma_results: Sigma waiver analysis results
        moments_results: Moments waiver analysis results
        root_path: Root directory to save analysis

    Returns:
        str: Path to combined analysis file
    """
    logging.info("Generating combined waiver analysis")

    try:
        combined_analysis = []
        combined_analysis.append("="*80)
        combined_analysis.append("COMBINED WAIVER ANALYSIS - SIGMA AND MOMENTS")
        combined_analysis.append("="*80)
        combined_analysis.append("")
        combined_analysis.append("This analysis combines results from both sigma and moments waiver systems")
        combined_analysis.append("to provide a comprehensive view of library characterization quality.")
        combined_analysis.append("")

        # Extract corner name function
        def extract_corner_from_filename(file_name):
            base_name = file_name.replace('.rpt', '').replace('MC_', '').replace('fmc_', '')
            import re
            corner_pattern = r'(ssg[ng][pg]_[0-9]p[0-9]+v_[mn][0-9]+c)'
            match = re.search(corner_pattern, base_name)
            if match:
                return match.group(1)
            return base_name.split('_')[0] if base_name else 'unknown'

        # Organize results by corner and type
        sigma_by_corner = {}
        moments_by_corner = {}

        for (file_name, type_name), data in sigma_results.items():
            corner = extract_corner_from_filename(file_name)
            if corner not in sigma_by_corner:
                sigma_by_corner[corner] = {}
            sigma_by_corner[corner][type_name] = data

        for (file_name, type_name), data in moments_results.items():
            corner = extract_corner_from_filename(file_name)
            if corner not in moments_by_corner:
                moments_by_corner[corner] = {}
            moments_by_corner[corner][type_name] = data

        # Compare results by corner
        all_corners = sorted(set(list(sigma_by_corner.keys()) + list(moments_by_corner.keys())))

        for corner in all_corners:
            combined_analysis.append(f"Corner: {corner}")
            combined_analysis.append("-" * 60)

            for type_name in ['delay', 'slew', 'hold']:
                if (corner in sigma_by_corner and type_name in sigma_by_corner[corner]) or \
                   (corner in moments_by_corner and type_name in moments_by_corner[corner]):

                    combined_analysis.append(f"\n{type_name.upper()} Analysis:")

                    # Sigma results
                    if corner in sigma_by_corner and type_name in sigma_by_corner[corner]:
                        sigma_data = sigma_by_corner[corner][type_name]
                        combined_analysis.append("  Sigma Results:")
                        for param, stats in sigma_data.items():
                            combined_analysis.append(f"    {param}: Base {stats['base_pr']:.1f}% | +Waiver1 {stats['pr_with_waiver1']:.1f}% | Opt Only {stats['pr_optimistic_only']:.1f}%")

                    # Moments results
                    if corner in moments_by_corner and type_name in moments_by_corner[corner]:
                        moments_data = moments_by_corner[corner][type_name]
                        combined_analysis.append("  Moments Results:")
                        for param, stats in moments_data.items():
                            combined_analysis.append(f"    {param}: Base {stats['base_pr']:.1f}% | +Waiver1 {stats['pr_with_waiver1']:.1f}% | Opt Only {stats['pr_optimistic_only']:.1f}%")

            combined_analysis.append("")

        # Save combined analysis
        analysis_file = os.path.join(root_path, "combined_waiver_analysis.txt")
        with open(analysis_file, 'w') as f:
            f.write('\n'.join(combined_analysis))

        logging.info(f"Combined waiver analysis saved to: {analysis_file}")
        return analysis_file

    except Exception as e:
        logging.error(f"Error generating combined waiver analysis", exc_info=True)
        return None