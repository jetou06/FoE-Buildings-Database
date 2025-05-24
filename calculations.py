import logging
from typing import Dict
import pandas as pd
import streamlit as st

# Import configurations and logger
from config import WEIGHTABLE_COLUMNS, logger
from translations import translate_era_key # Needed for reverse mapping

# --- Era Statistics Calculation --- (Cached in calling function)
# @st.cache_data # Cache decorator moved to the calling function in app.py
def calculate_era_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates min and max stats per era for weightable columns."""
    logger.info("Calculating min/max statistics per era...")
    if df.empty or 'Era' not in df.columns:
        logger.warning("Cannot calculate era stats: DataFrame is empty or missing 'Era' column.")
        return pd.DataFrame() # Return empty DataFrame if no data

    # Ensure weightable columns exist in the DataFrame
    cols_to_agg = [col for col in WEIGHTABLE_COLUMNS if col in df.columns]
    if not cols_to_agg:
        logger.warning("Cannot calculate era stats: No weightable columns found in DataFrame.")
        return pd.DataFrame()

    try:
        # Use standard min and max aggregation
        stats = df.groupby('Era')[cols_to_agg].agg(['min', 'max'])

        logger.info("Era statistics (min/max) calculation complete.")
        return stats
    except Exception as e:
        logger.error(f"Error calculating era statistics: {e}", exc_info=True)
        return pd.DataFrame() # Return empty on error

# --- Weighted Efficiency Calculation ---
def calculate_weighted_efficiency(df: pd.DataFrame, user_weights: Dict[str, float], era_stats_df: pd.DataFrame, df_original: pd.DataFrame, selected_translated_era: str, lang_code: str) -> pd.DataFrame:
    """Calculates the weighted efficiency score based on user weights and era stats."""
    logger.info(f"Calculating weighted efficiency for {len(df)} buildings in era '{selected_translated_era}'")

    norm_data = {}
    weighted_data = {}
    weighted_cols_list = []
    valid_weightable_cols = [col for col in WEIGHTABLE_COLUMNS if col in df.columns]

    if 'Era' not in df_original.columns:
        logger.error("Original DataFrame missing 'Era' column for reverse mapping. Cannot calculate efficiency.")
        df['Weighted Efficiency'] = -1.0
        return df

    try:
        unique_eras = df_original['Era'].unique()
        era_key_to_translated = {key: translate_era_key(key, lang_code) for key in unique_eras}
        translated_to_era_key = {v: k for k, v in era_key_to_translated.items()}
        raw_era_key = translated_to_era_key.get(selected_translated_era)
    except Exception as map_e:
        logger.error(f"Error creating era key mapping: {map_e}")
        df['Weighted Efficiency'] = -1.0
        return df

    if not raw_era_key:
        logger.error(f"Could not find raw era key for selected translated era: '{selected_translated_era}'. Skipping efficiency calculation.")
        df['Weighted Efficiency'] = -1.0
        return df
    elif era_stats_df.empty or raw_era_key not in era_stats_df.index:
         logger.warning(f"No stats found for raw era key: '{raw_era_key}' in era_stats_df. Skipping efficiency calculation.")
         df['Weighted Efficiency'] = 0.0
         return df

    for col in valid_weightable_cols:
        weight = user_weights.get(col, 0)
        if weight == 0: continue

        try:
            # Use 'min' and 'max' from the stats dataframe
            if (col, 'min') not in era_stats_df.columns or (col, 'max') not in era_stats_df.columns:
                logger.warning(f"Stats (min/max) not found for column '{col}' in era '{raw_era_key}'. Skipping.")
                continue
            norm_min = era_stats_df.loc[raw_era_key, (col, 'min')]
            norm_max = era_stats_df.loc[raw_era_key, (col, 'max')]
        except KeyError:
            logger.warning(f"KeyError accessing stats for era '{raw_era_key}', column '{col}'. Skipping.")
            continue
        except Exception as e:
             logger.error(f"Error looking up stats for era '{raw_era_key}', column '{col}': {e}. Skipping.")
             continue

        current_norm_col_data = pd.Series(0.0, index=df.index)
        if pd.isna(norm_min) or pd.isna(norm_max):
             logger.warning(f"NaN detected for norm_min/norm_max for column '{col}' in era '{raw_era_key}'. Skipping normalization.")
        elif norm_max > norm_min:
            # Standard Min-Max normalization
            current_norm_col_data = (df[col] - norm_min) / (norm_max - norm_min)
            # Clip to handle potential values outside original min/max if data changes
            current_norm_col_data = current_norm_col_data.clip(0, 1)
        elif norm_max == norm_min and norm_max > 0:
            # If min equals max and is positive, anything positive gets score 1
            current_norm_col_data = df[col].apply(lambda x: 1.0 if x > 0 else 0.0)
        # If min == max == 0, score remains 0.0

        norm_data[f"{col}_norm"] = current_norm_col_data
        weighted_data[f"{col}_weighted"] = current_norm_col_data * weight
        weighted_cols_list.append(f"{col}_weighted")

    if norm_data:
         try:
             norm_df = pd.DataFrame(norm_data, index=df.index)
             weighted_df = pd.DataFrame(weighted_data, index=df.index)
             df = pd.concat([df, norm_df, weighted_df], axis=1)

             if weighted_cols_list:
                  df['Total Score'] = df[weighted_cols_list].sum(axis=1)
                  # Normalize Total Score to 0-1000 range
                  min_score = df['Total Score'].min()
                  max_score = df['Total Score'].max()
                  if max_score > min_score:  # Avoid division by zero
                      df['Total Score'] = ((df['Total Score'] - min_score) / (max_score - min_score) * 1000).round(1)
                  else:
                      df['Total Score'] = 0  # If all scores are the same
                  
                  divisor = df['Nbr of squares (Avg)'].replace(0, 1)
                  # Calculate Weighted Efficiency
                  df['Weighted Efficiency'] = (df['Total Score'] / divisor).round(1)
                  # Remove intermediate columns
                  cols_to_drop = list(norm_df.columns) + list(weighted_df.columns) # Remove 'Total Score'
                  existing_cols_to_drop = [c for c in cols_to_drop if c in df.columns]
                  if existing_cols_to_drop:
                     df = df.drop(columns=existing_cols_to_drop)
                  logger.info("Weighted efficiency calculation complete. Retained 'Total Score'.")
             else:
                  df['Weighted Efficiency'] = 0.0
                  df['Total Score'] = 0.0 # Initialize Total Score if no weighted cols
                  logger.info("No weighted columns generated, Weighted Efficiency and Total Score set to 0.")
         except Exception as concat_err:
              logger.error(f"Error during final efficiency calculation/concat: {concat_err}", exc_info=True)
              df['Weighted Efficiency'] = -1.0
              df['Total Score'] = -1.0 # Indicate error
    else:
         df['Weighted Efficiency'] = 0.0
         df['Total Score'] = 0.0 # Initialize Total Score if no weights set
         logger.info("No valid columns to weight or no weights > 0, skipping efficiency calculation.")

    return df