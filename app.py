import logging
import os
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, ColumnsAutoSizeMode, AgGridTheme, GridUpdateMode, DataReturnMode, JsCode
from st_aggrid.grid_options_builder import GridOptionsBuilder
import json
import numpy as np

# --- Local Modules Imports ---
import config
import data_loader
import translations
import calculations
import ui_components
import column_selector
import advanced_filters
import data_visualizations
import building_images

# Use logger from config
logger = config.logger

def main():
    # --- Page Config ---
    st.set_page_config(
        layout="wide",
        page_title="FoE Building Database",
        page_icon=config.APP_ICON 
    )

    # --- Language Selection with Session State ---
    # Initialize language in session state if not exists
    if 'language' not in st.session_state:
        st.session_state.language = 'English'
    
    # Language selector with session state
    selected_language = st.sidebar.selectbox(
        "Select Language / Choisir la langue",
        options=list(translations.LANGUAGES.keys()),
        index=list(translations.LANGUAGES.keys()).index(st.session_state.language),
        key="language_selector"
    )
    
    # Update session state if language changed
    if selected_language != st.session_state.language:
        st.session_state.language = selected_language
        # Force rerun to update translations
        st.rerun()
    
    lang_code = translations.LANGUAGES[selected_language]

    # --- App Title and Description ---
    st.title(translations.get_text("title", lang_code))
    st.markdown(translations.get_text("description", lang_code))

    # --- Data Loading (Cached) ---
    @st.cache_data
    def load_cached_data():
        metadata_file_path = config.METADATA_FILE_PATH_TEMPLATE
        return data_loader.load_and_process_data(metadata_file_path)
    
    try:
        df_original = load_cached_data()

        if df_original.empty:
            st.warning("No building data loaded. Please check the metadata file and logs.")
            st.stop()

        # Round float columns (can be done earlier in data_loader if preferred)
        # float_cols = df_original.select_dtypes(include=['float64']).columns
        # df_original[float_cols] = df_original[float_cols].round(2)

        # --- Initial Data Transformation (Translations) ---
        @st.cache_data
        def apply_translations(df: pd.DataFrame, language_code: str) -> pd.DataFrame:
            df_translated = df.copy()
            
            # Translate building names
            if 'name' in df_translated.columns:
                df_translated['name'] = df_translated['name'].map(
                    lambda name: translations.translate_building_name(name, language_code)
                )
            else:
                logger.error("'name' column missing after data load.")

            # Translate event keys
            if 'Event' in df_translated.columns:
                df_translated['Event'] = df_translated['Event'].map(
                    lambda key: translations.translate_event_key(key, language_code)
                )
            else:
                logger.error("'Event' column missing after data load.")

            # Add Translated Era column
            if 'Era' in df_translated.columns:
                df_translated['Translated Era'] = df_translated['Era'].map(
                    lambda key: translations.translate_era_key(key, language_code)
                )
            else:
                logger.error("'Era' column not found after data load. Cannot translate eras.")
                df_translated['Translated Era'] = "Error"
            
            return df_translated
        
        # Apply cached translations
        df_original = apply_translations(df_original, lang_code)
        
        # Save translation file (only when needed)
        with open(os.path.join(config.TRANSLATIONS_PATH, "to_be_translated_building_names.json"), "w") as f:
            json.dump(translations.TO_BE_TRANSLATED_BUILDING_NAMES, f)

        # --- Pre-calculate Stats (Cached) ---
        # Apply cache decorator here as it depends on df_original
        @st.cache_data
        def cached_calculate_era_stats(df: pd.DataFrame) -> pd.DataFrame:
            return calculations.calculate_era_stats(df)
        
        era_stats_df = cached_calculate_era_stats(df_original)
        
        # --- Cache Building Images Manager ---
        @st.cache_resource
        def get_cached_image_manager():
            return building_images.get_image_manager()
        
        # Use cached image manager
        cached_image_manager = get_cached_image_manager()

        # --- Function to combine army stats ---
        def combine_army_with_ge_gbg(df: pd.DataFrame) -> pd.DataFrame:
            """Combine base army stats with GE/GBG equivalents and remove base columns."""
            df_combined = df.copy()
            
            # Define the mapping of base stats to their GE/GBG equivalents
            army_mappings = {
                'Red Attack': ['Red GE Attack', 'Red GBG Attack'],
                'Red Defense': ['Red GE Defense', 'Red GBG Defense'],
                'Blue Attack': ['Blue GE Attack', 'Blue GBG Attack'],
                'Blue Defense': ['Blue GE Defense', 'Blue GBG Defense']
            }
            
            for base_stat, target_stats in army_mappings.items():
                if base_stat in df_combined.columns:
                    base_values = df_combined[base_stat].fillna(0)
                    
                    # Add base values to GE and GBG equivalents
                    for target_stat in target_stats:
                        if target_stat in df_combined.columns:
                            df_combined[target_stat] = df_combined[target_stat].fillna(0) + base_values
                    
                    # Remove the base column
                    df_combined = df_combined.drop(columns=[base_stat])
            
            return df_combined

    except Exception as e:
        st.error(f"Failed during initial data loading or processing: {e}")
        logger.error(f"Failed during initial data load/process: {e}", exc_info=True)
        st.stop()

    # ================== Sidebar Configuration ==================
    st.sidebar.header(translations.get_text("filters", lang_code))

    # --- Era Filter ---
    # Get unique raw era keys and sort them according to ERAS_DICT order
    unique_raw_eras = df_original['Era'].unique()
    # Create a list of eras in ERAS_DICT order that exist in our data
    ordered_raw_eras = [era_key for era_key in config.ERAS_DICT.keys() if era_key in unique_raw_eras]
    # Add any eras that exist in data but not in ERAS_DICT (fallback)
    missing_eras = [era for era in unique_raw_eras if era not in config.ERAS_DICT.keys()]
    ordered_raw_eras.extend(sorted(missing_eras))  # Sort missing ones alphabetically as fallback
    
    # Translate the ordered era keys to get the properly ordered translated names
    available_eras = [translations.translate_era_key(era_key, lang_code) for era_key in ordered_raw_eras]
    
    default_translated_era = translations.translate_era_key("SpaceAgeSpaceHub", lang_code)
    try:
        default_era_index = available_eras.index(default_translated_era)
    except ValueError:
        default_era_index = 0
        logger.warning(f"Default translated era '{default_translated_era}' not found. Defaulting to index 0.")

    selected_translated_era = st.sidebar.selectbox(
        label=translations.translate_column("era", lang_code),
        options=available_eras,
        index=default_era_index,
        key="era_filter"
    )

    # --- Event Filter ---
    available_events = sorted(df_original['Event'].unique())
    selected_events = st.sidebar.multiselect(
        label=translations.translate_column("Event", lang_code),
        options=available_events,
        key="event_filter"
    )

    # --- Name Filter ---
    available_name_filters = sorted(df_original['name'].unique())
    name_filter = st.sidebar.multiselect(
        label=translations.get_text("search_label", lang_code),
        help=translations.get_text("search_help", lang_code),
        options=available_name_filters,
        key="name_filter"
    )

    # --- UI Options ---
    use_icons = st.sidebar.checkbox(translations.get_text("display_icons", lang_code), value=True, key="display_icons_checkbox")
    show_labels = st.sidebar.checkbox(translations.get_text("show_labels", lang_code), value=False, key="show_labels_checkbox") if use_icons else False
    show_per_square = st.sidebar.checkbox(translations.get_per_square_text(lang_code), value=False, key="per_square_checkbox")
    enable_heatmap = st.sidebar.checkbox(translations.get_text("enable_heatmap", lang_code), value=True, key="heatmap_checkbox")
    hide_zero_production = st.sidebar.checkbox(
        translations.get_text("hide_zero_production", lang_code), 
        value=False, 
        key="hide_zero_production_checkbox",
        help=translations.get_text("hide_zero_production_help", lang_code)
    )
    
    combine_army_stats = st.sidebar.checkbox(
        translations.get_text("combine_army_stats", lang_code),
        value=False,
        key="combine_army_stats_checkbox",
        help=translations.get_text("combine_army_stats_help", lang_code)
    )

    # --- Advanced Filters ---
    with st.sidebar:
        # Apply army stats combination to the dataframe used for filters if enabled
        df_for_filters = combine_army_with_ge_gbg(df_original) if combine_army_stats else df_original
        df_filtered_by_advanced = advanced_filters.render_advanced_filters(df_for_filters, lang_code, selected_translated_era)

    # --- Enhanced Column Selection ---
    with st.sidebar:
        # Apply army stats combination to the dataframe used for column selection if enabled
        df_for_columns = combine_army_with_ge_gbg(df_original) if combine_army_stats else df_original
        selected_columns = column_selector.render_enhanced_column_selector(df_for_columns, lang_code)

                    

    # --- Initialize Weights ---
    # Initialize weights dictionary before tabs
    user_weights = {}
    
    # ================== Main Content Area ==================
    tabs = st.tabs([
        translations.get_text("home", lang_code), 
        translations.get_text("weights", lang_code), 
        translations.get_text("building_details", lang_code),
        translations.get_text("visualizations", lang_code)
    ])
    
    # --- Weights Tab (Process this first) ---
    with tabs[1]:
        # Apply the same filtering as the Home tab for consistency
        df_viz_filtered = df_filtered_by_advanced[df_filtered_by_advanced['Translated Era'] == selected_translated_era].copy()
        if selected_events:
            df_viz_filtered = df_viz_filtered[df_viz_filtered['Event'].isin(selected_events)]
        if name_filter:
            df_viz_filtered = df_viz_filtered[df_viz_filtered['name'].isin(name_filter)]
        
        # Apply army stats combination if enabled
        if combine_army_stats:
            df_viz_filtered = combine_army_with_ge_gbg(df_viz_filtered)
        
        # Apply zero-production filter if enabled
        if hide_zero_production:
            basic_info_columns = config.COLUMN_GROUPS["basic_info"]["columns"]
            production_columns = [
                col for col in df_viz_filtered.columns 
                if col not in basic_info_columns
                and pd.api.types.is_numeric_dtype(df_viz_filtered[col])
            ]
            
            if production_columns:
                mask = (df_viz_filtered[production_columns] != 0).any(axis=1)
                df_viz_filtered = df_viz_filtered[mask]
        
        # Calculate efficiency if weights are set
        if any(w > 0 for w in user_weights.values()) and not df_viz_filtered.empty:
            df_viz_filtered = calculations.calculate_direct_weighted_efficiency(
                df=df_viz_filtered,
                user_weights=user_weights,
                user_context=user_context,
                user_boosts=user_boosts
            )
        
        # --- Weighting Inputs ---
        st.header(translations.get_text("efficiency_weights", lang_code))
        st.markdown(translations.get_text("efficiency_help_direct", lang_code))
        st.info(translations.get_text("reminder_city_context", lang_code))
        st.markdown("---")
        
        # Create two columns for better layout
        left_col, right_col = st.columns(2)
        
        # Split the column groups between the two columns
        column_groups_list = list(config.COLUMN_GROUPS.items())
        mid_point = len(column_groups_list) // 2
        
        for col, groups in [(left_col, column_groups_list[:mid_point]), (right_col, column_groups_list[mid_point:])]:
            with col:
                for group_key, group_info in groups:
                    # Find weightable columns within this group that exist in the data
                    cols_in_group = group_info["columns"]
                    inputs_to_create = []
                    for col_name in cols_in_group:
                        # Check if the column exists in the loaded data
                        if col_name in df_original.columns and col_name in config.WEIGHTABLE_COLUMNS:
                            # Check if the column is numeric before allowing weighting
                            if pd.api.types.is_numeric_dtype(df_original[col_name]):
                                inputs_to_create.append(col_name)

                    if inputs_to_create:  # Only show expander if there are inputs to create
                        with st.expander(translations.get_text(group_info["key"], lang_code), expanded=False):
                            for col_name in inputs_to_create:
                                # Skip boost metrics as they're now integrated into base metrics
                                if col_name in config.BOOST_TO_BASE_MAPPING:
                                    continue
                                    
                                help_text = f"Points per {translations.translate_column(col_name, lang_code).lower()}"
                                
                                user_weights[col_name] = st.number_input(
                                    label=f"1 {translations.translate_column(col_name, lang_code)} = ___ Points",
                                    help=help_text,
                                    value=0.0,
                                    min_value=0.0,
                                    step=0.1,
                                    format="%.1f",
                                    key=f"weight_{col_name}"
                                )
        st.markdown("---")
        # --- User Context Section ---
        st.header(translations.get_text("user_context", lang_code))
        st.markdown(translations.get_text("user_context_help", lang_code))
        
        # Base Production Section
        st.subheader(translations.get_text("base_production_section", lang_code))
        
        # Create two columns for base production inputs
        ctx_left_col, ctx_right_col = st.columns(2)
        
        user_context = {}
        context_fields = list(config.USER_CONTEXT_FIELDS.items())
        mid_point = len(context_fields) // 2
        
        for col, fields in [(ctx_left_col, context_fields[:mid_point]), (ctx_right_col, context_fields[mid_point:])]:
            with col:
                for field_key, field_config in fields:
                    user_context[field_key] = st.number_input(
                        label=translations.get_text(field_config["label_key"], lang_code),
                        help=translations.get_text(field_config["help_key"], lang_code),
                        value=float(field_config["default"]),
                        min_value=0.0,
                        step=1.0 if field_key in ["fp_daily_production", "medal_production", "special_goods_production", "guild_goods_production"] else 100.0,
                        key=f"context_{field_key}"
                    )
        
        # Current Boosts Section
        st.subheader(translations.get_text("current_boosts_section", lang_code))
        
        # Create two columns for boost inputs
        boost_left_col, boost_right_col = st.columns(2)
        
        user_boosts = {}
        boost_fields = list(config.USER_BOOST_FIELDS.items())
        boost_mid_point = len(boost_fields) // 2
        
        for col, fields in [(boost_left_col, boost_fields[:boost_mid_point]), (boost_right_col, boost_fields[boost_mid_point:])]:
            with col:
                for field_key, field_config in fields:
                    user_boosts[field_key] = st.number_input(
                        label=translations.get_text(field_config["label_key"], lang_code),
                        help=translations.get_text(field_config["help_key"], lang_code),
                        value=float(field_config["default"]),
                        min_value=0.0,
                        max_value=1000.0,
                        step=1.0,
                        format="%.1f",
                        key=f"boost_{field_key}"
                    )

        
        
    
    # --- Building Details Tab ---
    with tabs[2]:
        st.header(translations.get_text("building_stats", lang_code))
        
        # Filter buildings by selected era (same as Home tab)
        df_era_filtered = df_original[df_original['Translated Era'] == selected_translated_era].copy()

        # Create columns for layout
        col1, col2, col3 = st.columns([1,1,2])
        with col1:
            # Show currently selected era
            st.info(f"📍 {translations.translate_column('Era', lang_code)}: **{selected_translated_era}**", width=300)

            # Building selection dropdown (only buildings from selected era)
            building_names = sorted(df_era_filtered['name'].unique())
            selected_building = st.selectbox(
                label=translations.get_text("select_building", lang_code),
                options=[""] + building_names,
                index=0,
                key="building_selector"
            )

            st.markdown("---")
        
        # Apply army stats combination if enabled
        if combine_army_stats:
            df_era_filtered = combine_army_with_ge_gbg(df_era_filtered)
        
        
        
        if selected_building and selected_building != "":
            # Get the selected building data from the era-filtered dataframe
            building_data = df_era_filtered[df_era_filtered['name'] == selected_building].iloc[0]
            
            # Display building name as header
            st.markdown(f"### {selected_building}")
            
            # Function to check if an icon exists for a column
            def has_icon(col_name: str) -> bool:
                return col_name not in config.ICON_EXCLUDED_COLUMNS and ui_components.get_icon_base64(col_name) is not None
            
            # --- Complete Stats Table with Image ---
            st.subheader(f"📊 {translations.get_text('complete_stats_table', lang_code)}")
            
            # Prepare data for the stats table
            stats_data = []
            
            # Get all columns from column groups in order
            for group_key, group_info in config.COLUMN_GROUPS.items():
                for col in group_info["columns"]:
                    if col in building_data:
                        value = building_data[col]

                        # Skip zero values and empty strings, but keep all boolean values (including False)
                        is_boolean = isinstance(value, (bool, np.bool_))
                        if not is_boolean and (value == 0 or value == '' or pd.isna(value)):
                            continue
                        
                        # Get translated column name
                        translated_name = translations.translate_column(col, lang_code)
                        
                        # Format value
                        if col in config.PERCENTAGE_COLUMNS:
                            formatted_value = f"{value:.0f}%"
                        elif isinstance(value, float):
                            formatted_value = f"{value:.2f}" if value != int(value) else f"{int(value)}"
                        elif is_boolean:
                            formatted_value = translations.get_text("yes", lang_code) if value else translations.get_text("no", lang_code)
                        else:
                            formatted_value = str(value)
                        
                        # Check if column has an icon
                        icon_url = None
                        if col not in config.ICON_EXCLUDED_COLUMNS:
                            icon_base64 = ui_components.get_icon_base64(col)
                            if icon_base64:
                                icon_url = f"data:image/png;base64,{icon_base64}"
                        
                        stats_data.append({
                            "Icon": icon_url,
                            "Statistic": translated_name,
                            "Value": formatted_value
                        })
            
            # Create layout with stats table on left and image on right
            building_asset_id = building_data.get('asset_id')
            if building_asset_id and cached_image_manager.has_image(building_asset_id):
                # Layout with table on left and image on right
                table_col, img_col = st.columns([2, 4])
                
                with table_col:
                    if stats_data:
                        # Create DataFrame for the stats table
                        stats_df = pd.DataFrame(stats_data)
                        
                        # Display the stats table using Streamlit's dataframe with column config
                        st.dataframe(
                            stats_df,
                            column_config={
                                "Icon": st.column_config.ImageColumn(
                                    label="",
                                    width=None,
                                    pinned=True
                                ),
                                "Statistic": st.column_config.TextColumn(
                                    label=translations.get_text("stat_name", lang_code),
                                    width=None
                                ),
                                "Value": st.column_config.TextColumn(
                                    label=translations.get_text("value", lang_code),
                                    width=None
                                )
                            },
                            hide_index=True,
                            use_container_width=True,
                            height=40*len(stats_data) if len(stats_data) > 10 else None
                        )
                    else:
                        st.info(translations.get_text("no_stats_available", lang_code))
                
                with img_col:
                    image_url = cached_image_manager.get_building_image_url(building_asset_id)
                    st.image(
                        image_url,
                        caption=selected_building,
                        use_container_width=False
                    )
            else:
                # No image available, show table full width
                if stats_data:
                    # Create DataFrame for the stats table
                    stats_df = pd.DataFrame(stats_data)
                    
                    # Display the stats table using Streamlit's dataframe with column config
                    st.dataframe(
                        stats_df,
                        column_config={
                            "Icon": st.column_config.ImageColumn(
                                label="",
                                width=None,
                                pinned=True
                            ),
                            "Statistic": st.column_config.TextColumn(
                                label=translations.get_text("stat_name", lang_code),
                                width=None
                            ),
                            "Value": st.column_config.TextColumn(
                                label=translations.get_text("value", lang_code),
                                width=None
                            )
                        },
                        hide_index=True,
                        use_container_width=False,
                        height=40*len(stats_data) if len(stats_data) > 10 else None,
                        width=600
                    )
                else:
                    st.info(translations.get_text("no_stats_available", lang_code))
        else:
            st.info(translations.get_text("no_building_selected", lang_code))
    
    # --- Visualizations Tab ---
    with tabs[3]:
        # Apply the same filtering as the Home tab for consistency
        df_viz_filtered = df_filtered_by_advanced[df_filtered_by_advanced['Translated Era'] == selected_translated_era].copy()
        if selected_events:
            df_viz_filtered = df_viz_filtered[df_viz_filtered['Event'].isin(selected_events)]
        if name_filter:
            df_viz_filtered = df_viz_filtered[df_viz_filtered['name'].isin(name_filter)]
        
        # Apply army stats combination if enabled
        if combine_army_stats:
            df_viz_filtered = combine_army_with_ge_gbg(df_viz_filtered)
        
        # Apply zero-production filter if enabled
        if hide_zero_production:
            basic_info_columns = config.COLUMN_GROUPS["basic_info"]["columns"]
            production_columns = [
                col for col in df_viz_filtered.columns 
                if col not in basic_info_columns
                and pd.api.types.is_numeric_dtype(df_viz_filtered[col])
            ]
            
            if production_columns:
                mask = (df_viz_filtered[production_columns] != 0).any(axis=1)
                df_viz_filtered = df_viz_filtered[mask]
        
        # Calculate efficiency if weights are set
        if any(w > 0 for w in user_weights.values()) and not df_viz_filtered.empty:
            df_viz_filtered = calculations.calculate_direct_weighted_efficiency(
                df=df_viz_filtered,
                user_weights=user_weights,
                user_context=user_context,
                user_boosts=user_boosts
            )
        
        # Apply "Per Square" Calculation to visualization data if enabled
        if show_per_square and 'Nbr of squares (Avg)' in df_viz_filtered.columns and not df_viz_filtered.empty:
            numeric_cols = [
                col for col in df_viz_filtered.columns
                if col not in config.PER_SQUARE_EXCLUDED_COLUMNS
                and pd.api.types.is_numeric_dtype(df_viz_filtered[col])
            ]
            # Use divisor from the filtered df
            divisor_col = df_viz_filtered['Nbr of squares (Avg)']
            divisor_col = divisor_col.replace([0, pd.NA], 1).astype(float) # Avoid division by zero/NA

            for col in numeric_cols:
                if col in df_viz_filtered:
                    # Ensure column is numeric before dividing
                    if pd.api.types.is_numeric_dtype(df_viz_filtered[col]):
                        df_viz_filtered[col] = (df_viz_filtered[col] / divisor_col).round(8)
        
        # Render the visualizations
        data_visualizations.render_data_visualizations(df_viz_filtered, lang_code, show_per_square, combine_army_stats)
    
    # --- Home Tab ---
    with tabs[0]:
        try:
            # --- Filter Dataframe ---
            # Start with advanced filtered data
            df_filtered = df_filtered_by_advanced[df_filtered_by_advanced['Translated Era'] == selected_translated_era].copy()
            if selected_events:
                df_filtered = df_filtered[df_filtered['Event'].isin(selected_events)]
            if name_filter:
                df_filtered = df_filtered[df_filtered['name'].isin(name_filter)]

            # Apply army stats combination if enabled
            if combine_army_stats:
                df_filtered = combine_army_with_ge_gbg(df_filtered)

            # Debug logging for Event column
            logger.info(f"Columns in df_filtered: {df_filtered.columns.tolist()}")
            if 'Event' in df_filtered.columns:
                logger.info(f"Event column exists with values: {df_filtered['Event'].unique().tolist()}")
            else:
                logger.warning("Event column is missing from df_filtered")

            # --- Apply Zero-Production Filter ---
            buildings_filtered_by_zero_production = 0
            if hide_zero_production:
                # Get production columns (exclude basic_info group)
                basic_info_columns = config.COLUMN_GROUPS["basic_info"]["columns"]
                production_columns = [
                    col for col in selected_columns 
                    if col not in basic_info_columns and col in df_filtered.columns
                    and pd.api.types.is_numeric_dtype(df_filtered[col])
                ]
                
                if production_columns:
                    # Keep rows where at least one production column has non-zero value
                    mask = (df_filtered[production_columns] != 0).any(axis=1)
                    rows_before = len(df_filtered)
                    df_filtered = df_filtered[mask]
                    buildings_filtered_by_zero_production = rows_before - len(df_filtered)
                    logger.info(f"Zero-production filter: {buildings_filtered_by_zero_production} buildings hidden from {production_columns}")

            # --- Calculate Weighted Efficiency ---
            df_filtered['Weighted Efficiency'] = 0.0 # Initialize
            df_filtered['Total Score'] = 0.0 # Initialize
            any_weight_set = any(w > 0 for w in user_weights.values())
            if any_weight_set and not df_filtered.empty:
                df_filtered = calculations.calculate_direct_weighted_efficiency(
                    df=df_filtered,
                    user_weights=user_weights,
                    user_context=user_context,
                    user_boosts=user_boosts
                )
            elif not df_filtered.empty:
                logger.debug("Skipping efficiency calculation as no weights > 0 are set.")
            # If df_filtered is empty, WE column remains 0.0

            # --- Prepare Display Columns ---
            # selected_columns already contains the user's individual column selections
            
            # Filter columns that exist in the filtered dataframe
            existing_columns_for_display = []
            
            # Process selected columns in the order they were selected
            for col in selected_columns:
                if col in df_filtered.columns and col not in existing_columns_for_display:
                    existing_columns_for_display.append(col)
            
            # Ensure uniqueness while preserving order
            existing_columns_for_display = list(dict.fromkeys(existing_columns_for_display))
            logger.info(f"Columns selected for display: {existing_columns_for_display}")

            # Create the final DataFrame for AgGrid
            if not existing_columns_for_display:
                st.warning("No columns selected or available for display.")
                st.stop()
                
            df_display = df_filtered[existing_columns_for_display].copy()

            # --- Apply "Per Square" Calculation ---
            if show_per_square and 'Nbr of squares (Avg)' in df_filtered.columns:
                numeric_cols = [
                    col for col in df_display.columns
                    if col not in config.PER_SQUARE_EXCLUDED_COLUMNS
                    and pd.api.types.is_numeric_dtype(df_display[col])
                ]
                # Use divisor from the filtered df *before* potential division
                divisor_col = df_filtered.loc[df_display.index, 'Nbr of squares (Avg)']
                divisor_col = divisor_col.replace([0, pd.NA], 1).astype(float) # Avoid division by zero/NA

                for col in numeric_cols:
                    if col in df_display:
                        # Ensure column is numeric before dividing
                        if pd.api.types.is_numeric_dtype(df_display[col]):
                            df_display[col] = (df_display[col] / divisor_col).round(8)
                        else:
                            logger.warning(f"Column '{col}' intended for per-square calc is not numeric.")

            # --- Configure and Display AgGrid ---
            eff_min = df_display['Weighted Efficiency'].min() if 'Weighted Efficiency' in df_display and not df_display.empty else 0
            eff_max = df_display['Weighted Efficiency'].max() if 'Weighted Efficiency' in df_display and not df_display.empty else 0
            if pd.isna(eff_min): eff_min = 0
            if pd.isna(eff_max): eff_max = 0

            # --- Prepare Export DataFrame with Translated Column Names ---
            df_export = df_display.copy()
            # Create mapping of original to translated column names
            column_translation_map = {
                col: translations.translate_column(col, lang_code) 
                for col in df_export.columns
            }
            # Rename columns to translated names
            df_export.rename(columns=column_translation_map, inplace=True)
            logger.info(f"Column translations for export: {column_translation_map}")

            # --- Export Buttons ---
            col1, col2 = st.columns([1, 10])
            with col1:
                # CSV Export with proper UTF-8 encoding and BOM
                buffer_csv = BytesIO()
                # Add UTF-8 BOM manually
                buffer_csv.write('\ufeff'.encode('utf-8'))
                # Write CSV data with translated column names
                csv_string = df_export.to_csv(index=False, sep=";")
                buffer_csv.write(csv_string.encode('utf-8'))
                buffer_csv.seek(0)
                csv_data = buffer_csv.getvalue()
                
                st.download_button(
                    label=translations.get_text("export_csv", lang_code),
                    data=csv_data,
                    file_name=f"foe_buildings_{selected_translated_era}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv",
                    mime="text/csv; charset=utf-8",
                    key="export_csv"
                )
            with col2:
                # JSON Export with translated column names and proper UTF-8 encoding
                json_string = df_export.to_json(orient="records", date_format="iso", force_ascii=False)
                json_data = json_string.encode('utf-8')
                
                st.download_button(
                    label=translations.get_text("export_json", lang_code),
                    data=json_data,
                    file_name=f"foe_buildings_{selected_translated_era}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json",
                    mime="application/json; charset=utf-8",
                    key="export_json"
                )

            grid_options = ui_components.build_grid_options(
                df_display=df_display,
                lang_code=lang_code,
                use_icons=use_icons,
                show_labels=show_labels,
                enable_heatmap=enable_heatmap,
                eff_min=eff_min,
                eff_max=eff_max
            )
            
            # --- Display Filter Information ---
            if hide_zero_production and buildings_filtered_by_zero_production > 0:
                st.info(
                    translations.get_text("zero_production_filter_info", lang_code).format(
                        count=buildings_filtered_by_zero_production
                    )
                )

            # --- Create a dynamic key to force re-render and auto-sizing when switching language ---
            grid_key = f"building_grid_{lang_code}"
            logger.debug(f"Using AgGrid key: {grid_key}")

            grid_return = AgGrid(
                df_display,
                gridOptions=grid_options,
                custom_css=ui_components.CUSTOM_CSS,
                allow_unsafe_jscode=True,
                theme=AgGridTheme.STREAMLIT,
                height=800,
                width='100%',
                reload_data=False,
                key=grid_key,
                update_mode=GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS
            )

            # --- Display Disclaimer ---
            st.markdown("***")
            st.markdown(translations.get_text("efficiency_disclaimer", lang_code))
            
            # --- Credits Section ---
            st.markdown("***")
            st.markdown(translations.get_text("credits_title", lang_code))
            
            # Create columns for credits layout
            credits_col1, credits_col2 = st.columns(2)
            
            with credits_col1:
                st.markdown(f"**{translations.get_text('data_sources', lang_code)}**")
                st.markdown(f"- {translations.get_text('foe_buildings_db', lang_code)}")
                st.markdown(f"- {translations.get_text('innogames_foe', lang_code)}")
                
                st.markdown(f"**{translations.get_text('development_tools', lang_code)}**")
                st.markdown(f"- [Streamlit](https://streamlit.io/) - {translations.get_text('web_framework', lang_code)}")
                st.markdown(f"- [AG-Grid](https://www.ag-grid.com/) - {translations.get_text('data_grid', lang_code)}")
                st.markdown(f"- [Pandas](https://pandas.pydata.org/) - {translations.get_text('data_analysis', lang_code)}")
            
            with credits_col2:
                st.markdown(f"**{translations.get_text('community', lang_code)}**")
                st.markdown(f"- {translations.get_text('foe_community', lang_code)}")
                st.markdown(f"- {translations.get_text('beta_testers', lang_code)}")
                
                st.markdown(f"**{translations.get_text('special_thanks', lang_code)}**")
                st.markdown(f"- {translations.get_text('github_contributors', lang_code)}")
            
            # Footer
            st.markdown("---")
            st.markdown(
                f"<div style='text-align: center; color: #666; font-size: 0.9em;'>"
                f"{translations.get_text('made_with_love', lang_code)} | "
                f"{translations.get_text('not_affiliated', lang_code)}"
                f"</div>", 
                unsafe_allow_html=True
            )

        except Exception as e:
            st.error(f"An error occurred during app execution: {str(e)}")
            logger.error(f"Error during main app execution: {e}", exc_info=True)

# --- Main Execution Guard ---
if __name__ == "__main__":
    main()