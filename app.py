import logging
import os

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, ColumnsAutoSizeMode, AgGridTheme, GridUpdateMode, DataReturnMode, JsCode
from st_aggrid.grid_options_builder import GridOptionsBuilder
import json

# --- Local Modules Imports ---
import config
import data_loader
import translations
import calculations
import ui_components

# Use logger from config
logger = config.logger

def main():
    # --- Page Config ---
    st.set_page_config(
        layout="wide",
        page_title="FoE Building Analyzer",
        page_icon=config.APP_ICON 
    )

    # --- Language Selection ---
    selected_language = st.sidebar.selectbox(
        "Select Language / Choisir la langue",
        options=list(translations.LANGUAGES.keys()),
        index=0 # Default to English
    )
    lang_code = translations.LANGUAGES[selected_language]

    # --- App Title and Description ---
    st.title(translations.get_text("title", lang_code))
    st.markdown(translations.get_text("description", lang_code))

    # --- Data Loading ---
    try:
        # username = os.getlogin()
        metadata_file_path = config.METADATA_FILE_PATH_TEMPLATE
        df_original = data_loader.load_and_process_data(metadata_file_path)

        if df_original.empty:
            st.warning("No building data loaded. Please check the metadata file and logs.")
            st.stop()

        # Round float columns (can be done earlier in data_loader if preferred)
        # float_cols = df_original.select_dtypes(include=['float64']).columns
        # df_original[float_cols] = df_original[float_cols].round(2)

        # --- Initial Data Transformation (Translations) ---
        # Translate building names
        if 'name' in df_original.columns:
            df_original['name'] = df_original['name'].map(
                lambda name: translations.translate_building_name(name, lang_code)
            )
        else:
             logger.error("'name' column missing after data load.")

        with open(os.path.join(config.TRANSLATIONS_PATH, "to_be_translated_building_names.json"), "w") as f:
            json.dump(translations.TO_BE_TRANSLATED_BUILDING_NAMES, f)

        # Translate event keys
        if 'Event' in df_original.columns:
            df_original['Event'] = df_original['Event'].map(
                lambda key: translations.translate_event_key(key, lang_code)
            )
        else:
            logger.error("'Event' column missing after data load.")

        # Add Translated Era column
        if 'Era' in df_original.columns:
            df_original['Translated Era'] = df_original['Era'].map(
                lambda key: translations.translate_era_key(key, lang_code)
            )
        else:
            st.error("'Era' column not found after data load. Cannot translate eras.")
            df_original['Translated Era'] = "Error"

        # --- Pre-calculate Stats (Cached) ---
        # Apply cache decorator here as it depends on df_original
        @st.cache_data
        def cached_calculate_era_stats(df: pd.DataFrame) -> pd.DataFrame:
            return calculations.calculate_era_stats(df)
        
        era_stats_df = cached_calculate_era_stats(df_original)

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
        label=translations.translate_column("Era", lang_code),
        options=available_eras,
        index=default_era_index,
        key="era_filter"
    )

    # --- Event Filter ---
    available_events = sorted(df_original['Event'].unique())
    selected_event = st.sidebar.selectbox(
        label=translations.translate_column("Event", lang_code),
        options=[translations.get_text("all_events", lang_code)] + available_events,
        index=0,
        key="event_filter"
    )

    # --- Name Filter ---
    name_filter = st.sidebar.text_input(translations.get_text("search_label", lang_code)).lower()

    # --- UI Options ---
    use_icons = st.sidebar.checkbox(translations.get_text("display_icons", lang_code), value=True, key="display_icons_checkbox")
    show_labels = st.sidebar.checkbox(translations.get_text("show_labels", lang_code), value=False, key="show_labels_checkbox") if use_icons else False
    show_per_square = st.sidebar.checkbox(translations.get_per_square_text(lang_code), value=False, key="per_square_checkbox")
    enable_heatmap = st.sidebar.checkbox(translations.get_text("enable_heatmap", lang_code), value=True, key="heatmap_checkbox")

    # --- Column Group Selection ---
    st.sidebar.header(translations.get_text("column_selection", lang_code))
    selected_group_keys = st.sidebar.multiselect(
        translations.get_text("select_groups", lang_code),
        options=list(config.COLUMN_GROUPS.keys()),
        default=["basic_info"],
        format_func=lambda key: translations.get_text(key, lang_code)
    )

    # --- Initialize Weights ---
    # Initialize weights dictionary before tabs
    user_weights = {}
    
    # ================== Main Content Area ==================
    tabs = st.tabs([translations.get_text("home", lang_code), translations.get_text("weights", lang_code)])
    
    # --- Weights Tab (Process this first) ---
    with tabs[1]:
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
        
        st.markdown("---")
        
        # --- Weighting Inputs ---
        st.header(translations.get_text("efficiency_weights", lang_code))
        st.markdown(translations.get_text("efficiency_help_direct", lang_code))
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
    
    # --- Home Tab ---
    with tabs[0]:
        try:
            # --- Filter Dataframe ---
            df_filtered = df_original[df_original['Translated Era'] == selected_translated_era].copy()
            if selected_event != translations.get_text("all_events", lang_code):
                df_filtered = df_filtered[df_filtered['Event'] == selected_event]
            if name_filter:
                df_filtered = df_filtered[df_filtered['name'].str.lower().str.contains(name_filter)]

            # Debug logging for Event column
            logger.info(f"Columns in df_filtered: {df_filtered.columns.tolist()}")
            if 'Event' in df_filtered.columns:
                logger.info(f"Event column exists with values: {df_filtered['Event'].unique().tolist()}")
            else:
                logger.warning("Event column is missing from df_filtered")

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
            selected_columns = ['name']  # Start with name
            
            # Add columns from selected groups
            for group_key in selected_group_keys:
                group_columns = config.COLUMN_GROUPS[group_key]["columns"]
                selected_columns.extend(group_columns)

            # Filter columns that exist in the filtered dataframe
            existing_columns_for_display = []
            
            # Always include name first if it exists
            if 'name' in df_filtered.columns:
                existing_columns_for_display.append('name')
            
            # Add other columns in order
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

            # --- Export Buttons ---
            col1, col2 = st.columns([1, 10])
            with col1:
                # CSV Export
                csv = df_display.to_csv(index=False, sep=";")
                st.download_button(
                    label=translations.get_text("export_csv", lang_code),
                    data=csv,
                    file_name=f"foe_buildings_{selected_translated_era}.csv",
                    mime="text/csv",
                    key="export_csv"
                )
            with col2:
                # JSON Export
                json_str = df_display.to_json(orient="records", date_format="iso")
                st.download_button(
                    label=translations.get_text("export_json", lang_code),
                    data=json_str,
                    file_name=f"foe_buildings_{selected_translated_era}.json",
                    mime="application/json",
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

            # --- Create a dynamic key to force re-render and auto-sizing ---
            grid_key = f"building_grid_{selected_translated_era}_{name_filter}_{any_weight_set}_{show_per_square}_{lang_code}_{'_'.join(sorted(selected_group_keys))}"
            logger.debug(f"Using AgGrid key: {grid_key}")

            grid_return = AgGrid(
                df_display,
                gridOptions=grid_options,
                custom_css=ui_components.CUSTOM_CSS,
                allow_unsafe_jscode=True,
                theme=AgGridTheme.STREAMLIT,
                height=800,
                width='100%',
                reload_data=True,
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