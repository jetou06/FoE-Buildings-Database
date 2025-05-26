import json
import logging
import os
import sqlite3
from typing import Dict, List, Tuple, Any
import requests as r

import pandas as pd
import streamlit as st

# Import configurations
from config import DB_PATH, ASSETS_PATH, logger

# --- Database Connection Management ---
@st.cache_resource
def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Get a cached database connection."""
    logger.info(f"Attempting to connect to database: {db_path}")
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False) # Allow connection across threads for Streamlit
        conn.row_factory = sqlite3.Row
        logger.info(f"Successfully connected to database: {db_path}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error to {db_path}: {e}")
        st.error(f"Database error: {str(e)}")
        raise # Reraise critical error

# --- Building Data Processing Class ---
# Assuming the optimized BuildingAnalyzer that parses directly to dicts
class BuildingAnalyzer:
    """Manages the analysis of FoE buildings directly from JSON."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        # Store data as a list of dictionaries directly
        self.building_data_list: List[Dict[str, Any]] = []
        self.df = None

    # --- Helper methods moved from Building class (static or adapted) ---

    @staticmethod
    def _calculate_size_data(components: Dict) -> Tuple[int, int, str, float, bool]:
        """Calculate size data directly from components."""
        placement_size = components.get('AllAge', {}).get('placement', {}).get('size', {})
        height = placement_size.get('y', 0)
        width = placement_size.get('x', 0)
        size_string = f"{height}x{width}"
        needs_road = 'streetConnectionRequirement' in components.get('AllAge', {})
        total_squares = float(height * width)
        if needs_road:
            total_squares += min(width, height) / 2
        return width, height, size_string, total_squares, needs_road

    @staticmethod
    def _check_limitations(components: Dict) -> str:
        """Check limitations directly from components."""
        limited_comp = components.get('AllAge', {}).get('limited')
        if not limited_comp:
            return "No"
        limited_config = limited_comp.get('config', {})
        if 'expireTime' in limited_config:
            days = int(limited_config['expireTime'] / 86400)
            return f"Yes - {days} days"
        elif 'collectionAmount' in limited_config:
            collections = limited_config['collectionAmount']
            return f"Yes - {collections} collections"
        return "Yes - Other"

    @staticmethod
    def _get_ally_room(components: Dict) -> str:
        """Get ally room directly from components."""
        ally_comp = components.get('AllAge', {}).get('ally')
        if not ally_comp:
            return 'No'
        room = ally_comp.get('rooms', [{}])[0]
        ally_type = room.get('allyType', 'Unknown').capitalize()
        if 'rarity' in room:
            rarity = room.get('rarity', {}).get('value', 'Unknown').capitalize()
            return f"{ally_type} - {rarity}"
        return f"{ally_type} - Any rarity"

    @staticmethod
    def _get_pop_happiness(components: Dict, era_key: str) -> Tuple[int, int]:
        """Get population/happiness directly from components for a specific era."""
        pop = happiness = 0
        # Combine data from era_key and 'AllAge'
        for component_key in [era_key, 'AllAge']:
            component_data = components.get(component_key, {})
            if not component_data: continue

            # Get Population (more robust checks)
            static_resources = component_data.get('staticResources', {})
            if isinstance(static_resources, dict):
                resources = static_resources.get('resources', {})
                if isinstance(resources, dict):
                    resources_data = resources.get('resources', {})
                    if isinstance(resources_data, dict):
                         current_pop = resources_data.get('population', 0)
                         # Use the value if it's non-zero, prevents overwriting with 0 from AllAge
                         if current_pop != 0: pop = current_pop

            # Get Happiness (more robust checks)
            happiness_data = component_data.get('happiness', {})
            if isinstance(happiness_data, dict):
                current_happiness = happiness_data.get('provided', 0)
                # Use the value if it's non-zero
                if current_happiness != 0: happiness = current_happiness
        return pop, happiness

    @staticmethod
    def _get_production_data(components: Dict, era_key: str, building_name: str) -> Dict[str, Any]:
        """Calculate production values directly for a specific era."""
        production = {
            'coins': 0.0, 'supplies': 0.0, 'medals': 0.0, 'forge_points': 0.0, 'forgepoint_package': 0.0,
            'goods': 0.0, 'next_age_goods': 0.0, 'prev_age_goods': 0.0, 'special_goods': 0.0, 'guild_goods': 0.0,
            'units_amount': 0.0, 'units_type': "", 'fast_units': 0.0, 'heavy_units': 0.0, 'ranged_units': 0.0,
            'artillery_units': 0.0, 'light_units': 0.0, 'rogues_units': 0.0,
            'next_age_units_amount': 0.0, 'next_age_units_type': "", 'next_age_fast_units': 0.0,
            'next_age_heavy_units': 0.0, 'next_age_ranged_units': 0.0, 'next_age_artillery_units': 0.0,
            'next_age_light_units': 0.0, 'finish_special_production': 0.0, 'finish_goods_production': 0.0,
            'store_kit': 0.0, 'mass_self_aid_kit': 0.0, 'self_aid_kit': 0.0, 'renovation_kit': 0.0,
            'one_up_kit': 0.0, 'finish_all_supplies': 0.0,
            'other_items': [] # Intermediate storage for other items
        }
        prod_map = { # Mapping from JSON keys to production dict keys
            'money': 'coins', 'supplies': 'supplies', 'medals': 'medals', 'strategy_points': 'forge_points',
            'forgepoint_package': 'forgepoint_package',
            'all_goods_of_age': 'goods', 'random_good_of_age': 'goods',
            'all_goods_of_previous_age': 'prev_age_goods', 'random_good_of_previous_age': 'prev_age_goods',
            'all_goods_of_next_age': 'next_age_goods', 'random_good_of_next_age': 'next_age_goods', 'random_special_good_up_to_age': 'special_goods'
        }
        guild_prod_map = { # Mapping from JSON keys to production dict keys
            'all_goods_of_age': 'guild_goods'
        }
        unit_type_map = {
            'heavy_melee': "Heavy", 'fast': "Fast", 'short_ranged': "Ranged",
            'long_ranged': "Artillery", 'light_melee': "Light"
        }
        consumables_map = {
            'rush_event_buildings_instant': 'finish_special_production',
            'rush_goods_buildings_instant': 'finish_goods_production',
            'store_building': 'store_kit',
            'mass_self_aid_kit': 'mass_self_aid_kit',
            'self_aid_kit': 'self_aid_kit',
            'renovation_kit': 'renovation_kit',
            'one_up_kit': 'one_up_kit',
            'rush_mass_supplies_24h': 'finish_all_supplies'
        }
        units = {'Fast': 0.0, 'Heavy': 0.0, 'Light': 0.0, 'Ranged': 0.0, 'Artillery': 0.0}
        next_age_units = {'Fast': 0.0, 'Heavy': 0.0, 'Light': 0.0, 'Ranged': 0.0, 'Artillery': 0.0}
        goods_next_temp = 0.0
        goods_prev_temp = 0.0
        goods_special_temp = 0.0
        rogues_temp = 0.0
        other_items_temp = []
        guild_goods_temp = 0.0 # Added missing temp var

        for component_key in [era_key, 'AllAge']:
            component_data = components.get(component_key, {})
            prod_component = component_data.get('production', {})
            if not prod_component: continue
            lookup_rewards = component_data.get('lookup', {}).get('rewards', {})

            for option in prod_component.get('options', [{}])[0].get('products', []):
                if not isinstance(option, dict): continue
                option_type = option.get('type')
                # Drop chance default 1.0 for non-random base items, use actual if present
                drop_chance = float(option.get("dropChance", 1.0) if option_type != 'random' else 1.0)

                if option_type == 'resources':
                    resources = option.get('playerResources', {}).get('resources', {})
                    if isinstance(resources, dict):
                        for json_key, amount in resources.items():
                            if json_key in prod_map:
                                production[prod_map[json_key]] += float(amount)
                                

                elif option_type == 'unit':
                     unit_id = option.get('unitTypeId')
                     amount = float(option.get('amount', 0))
                     if unit_id == 'rogue':
                         rogues_temp += amount
                     elif unit_id in unit_type_map:
                         units[unit_type_map[unit_id]] += amount
                     elif unit_id and "NextEra" in unit_id:
                        cleaned_id = unit_id.replace("NextEra","") # Attempt to clean
                        if cleaned_id in unit_type_map:
                            next_age_units[unit_type_map[cleaned_id]] += amount

                elif option_type == 'guildResources':
                    resources = option.get('guildResources', {}).get('resources', {})
                    if isinstance(resources, dict):
                        for json_key, amount in resources.items():
                            if json_key in guild_prod_map:
                                production[guild_prod_map[json_key]] += float(amount)

                elif option_type == 'genericReward':
                    reward_id = option.get('reward', {}).get('id')
                    reward_lookup = lookup_rewards.get(reward_id)
                    if not reward_lookup: 
                        continue
                    reward_type = reward_lookup.get('type')
                    reward_amount = float(reward_lookup.get('totalAmount', reward_lookup.get('amount', reward_lookup.get('totalAmount', 0))))

                    if reward_type == 'consumable':
                        reward_subtype = reward_lookup.get('subType')
                        if reward_subtype == 'fragment':
                            reward_id = reward_lookup.get('assembledReward', {}).get('id')
                            if reward_id in consumables_map.keys():
                                reward_amount = float(reward_amount) / reward_lookup.get('requiredAmount', 1)
                                production[consumables_map[reward_id]] += reward_amount
                            else:
                                other_items_temp.append(reward_lookup.get('name', 'Unknown Consumable'))
                        elif reward_id in consumables_map.keys():
                            production[consumables_map[reward_id]] += reward_amount
                        else:
                            other_items_temp.append(reward_lookup.get('name', 'Unknown Consumable'))
                    elif reward_type == 'set':
                        reward_id = reward_lookup.get('rewards', [{}])[0].get('id')
                        if reward_id in consumables_map.keys():
                            reward_amount = float(reward_amount)
                            production[consumables_map[reward_id]] += reward_amount
                        else:
                            other_items_temp.append(reward_lookup.get('name', 'Unknown Consumable'))
                    elif reward_type in ['good', 'special_goods', 'guild_goods']:
                        if 'Current' in reward_id: 
                            production['goods'] += reward_amount
                        elif 'special' in reward_id: 
                            goods_special_temp += reward_amount
                        elif 'Next' in reward_id: 
                            goods_next_temp += reward_amount
                        elif 'Previous' in reward_id: 
                            goods_prev_temp += reward_amount
                        elif 'guild_goods' in reward_id: 
                            guild_goods_temp += reward_amount
                    elif reward_type == 'unit':
                        is_handled = False
                        if "rogue" in reward_id: rogues_temp += reward_amount; is_handled = True
                        if not is_handled:
                            for unit_json_id, unit_name in unit_type_map.items():
                                if unit_json_id in reward_id:
                                    if "Current" in reward_id: units[unit_name] += reward_amount; is_handled = True; break
                                    elif "NextEra" in reward_id: next_age_units[unit_name] += reward_amount; is_handled = True; break
                    elif reward_type == 'chest':
                        possible = reward_lookup.get('possible_rewards', [{}])[0]
                        first_reward_data = possible.get('reward',{})
                        first_reward_amount = float(first_reward_data.get('amount', first_reward_data.get('totalAmount', 0)))
                        
                        first_reward_type = first_reward_data.get('type')
                        if ('NextEra' in reward_id) and first_reward_type == 'good':
                            goods_next_temp += first_reward_amount
                        elif 'next_age_unit' in reward_id:
                             for unit_json_id, unit_name in unit_type_map.items():
                                next_age_units[unit_name] += first_reward_amount * possible.get('drop_chance', 100) / 100.0
                        elif 'random_unit' in reward_id:
                             for unit_json_id, unit_name in unit_type_map.items():
                                units[unit_name] += first_reward_amount * possible.get('drop_chance', 100) / 100.0; break
                    elif 'forgepoint_package' in reward_id:
                        fp_val = 0
                        if 'large' in reward_id: fp_val = 10
                        elif 'medium' in reward_id: fp_val = 5
                        elif 'small' in reward_id: fp_val = 2
                        production['forgepoint_package'] += fp_val * reward_amount

                elif option_type == 'random':
                    products_in_random = option.get("products", [])
                    for product in products_in_random:
                         if not isinstance(product, dict): continue
                         product_data = product.get('product', {})
                         prod_drop_chance = float(product.get("dropChance", 0))
                         if prod_drop_chance == 0: 
                             logger.warning(f"Drop chance is 0 for {building_name}")
                             continue

                         prod_type = product_data.get('type')
                         if prod_type == 'resources':
                             resources = product_data.get('playerResources', {}).get('resources', {})
                             if isinstance(resources, dict):
                                 for json_key, amount in resources.items():
                                     if json_key in prod_map:
                                         production[prod_map[json_key]] += float(amount) * prod_drop_chance
                                     elif json_key == 'guild_goods':
                                         guild_goods_temp += float(amount) * prod_drop_chance
                         elif prod_type == 'genericReward':
                            reward_id = product_data.get('reward', {}).get('id')
                            reward_lookup = lookup_rewards.get(reward_id)
                            if not reward_lookup: continue
                            reward_type = reward_lookup.get('type')
                            reward_amount = float(reward_lookup.get('totalAmount', reward_lookup.get('amount', reward_lookup.get('totalAmount', 0))))

                            if reward_type == 'consumable':
                                reward_subtype = reward_lookup.get('subType')
                                if reward_subtype == 'fragment':
                                    reward_id = reward_lookup.get('assembledReward', {}).get('id')
                                    if reward_id in consumables_map.keys():
                                        reward_amount = float(reward_amount) / reward_lookup.get('requiredAmount', 1)
                                        production[consumables_map[reward_id]] += reward_amount * prod_drop_chance
                                    else:
                                        other_items_temp.append(f"{reward_lookup.get('name', 'Unknown Consumable')} ({int(prod_drop_chance*100)}%)")
                                elif reward_id in consumables_map.keys():
                                    production[consumables_map[reward_id]] += reward_amount * prod_drop_chance
                                else:
                                    other_items_temp.append(f"{reward_lookup.get('name', 'Unknown Consumable')} ({int(prod_drop_chance*100)}%)")
                            elif reward_type == 'set':
                                reward_id = reward_lookup.get('rewards', [{}])[0].get('id')
                                if reward_id in consumables_map.keys():
                                    reward_amount = float(reward_amount)
                                    production[consumables_map[reward_id]] += reward_amount * prod_drop_chance
                                else:
                                    other_items_temp.append(f"{reward_lookup.get('name', 'Unknown Consumable')} ({int(prod_drop_chance*100)}%)")
                            elif reward_type in ['good', 'special_goods', 'guild_goods']:
                                if 'Current' in reward_id: production['goods'] += reward_amount * prod_drop_chance
                                elif 'special' in reward_id: goods_special_temp += reward_amount * prod_drop_chance
                                elif 'Next' in reward_id: goods_next_temp += reward_amount * prod_drop_chance
                                elif 'Previous' in reward_id: goods_prev_temp += reward_amount * prod_drop_chance
                                elif 'guild_goods' in reward_id: guild_goods_temp += reward_amount * prod_drop_chance
                            elif reward_type == 'unit':
                                if component_key == 'AllAge': continue
                                is_handled = False
                                if "rogue" in reward_id: rogues_temp += reward_amount * prod_drop_chance; is_handled = True
                                if not is_handled:
                                    for unit_json_id, unit_name in unit_type_map.items():
                                        if unit_json_id in reward_id:
                                            if "Current" in reward_id: units[unit_name] += reward_amount * prod_drop_chance; is_handled = True; break
                                            elif "NextEra" in reward_id: next_age_units[unit_name] += reward_amount * prod_drop_chance; is_handled = True; break
                            elif reward_type == 'chest':
                                possible = reward_lookup.get('possible_rewards', [{}])[0]
                                first_reward_data = possible.get('reward',{})
                                first_reward_amount = float(first_reward_data.get('amount', first_reward_data.get('totalAmount', 0)))
                                first_reward_type = first_reward_data.get('type')
                                chest_inner_chance = float(possible.get('drop_chance', 100)) / 100.0
                                effective_chance = prod_drop_chance * chest_inner_chance
                                if ('NextEra' in reward_id or 'next_age' in reward_id) and first_reward_type == 'good':
                                    goods_next_temp += first_reward_amount * effective_chance
                                elif 'next_age_unit' in reward_id:
                                    for unit_json_id, unit_name in unit_type_map.items():
                                        if unit_json_id in reward_id or unit_json_id in first_reward_data.get('id',''):
                                            next_age_units[unit_name] += first_reward_amount * effective_chance; break
                                elif 'random_unit' in reward_id:
                                    for unit_json_id, unit_name in unit_type_map.items():
                                        if unit_json_id in reward_id or unit_json_id in first_reward_data.get('id',''):
                                            units[unit_name] += first_reward_amount * effective_chance; break
                            elif 'forgepoint_package' in reward_id:
                                fp_val = 0
                                if 'large' in reward_id: fp_val = 10
                                elif 'medium' in reward_id: fp_val = 5
                                elif 'small' in reward_id: fp_val = 2
                                production['forgepoint_package'] += fp_val * reward_amount * prod_drop_chance
                            else:
                                other_items_temp.append(f"{product_data.get('name', 'Unknown Reward')} ({int(prod_drop_chance*100)}%)") 
        # Aggregate temporary values
        production['guild_goods'] += guild_goods_temp
        production['next_age_goods'] += goods_next_temp
        production['prev_age_goods'] += goods_prev_temp
        if era_key in ['BronzeAge', 'IronAge', 'HighMiddleAge', 'LateMiddleAge', 'ColonialAge', 'ProgressiveEra', 'IndustrialAge', 'ModernEra', 'PostModernEra', 'ContemporaryEra', 'TomorrowEra', 'FutureEra']:
            production['next_age_goods'] += production['special_goods']
            production['special_goods'] = 0
        else:
            production['special_goods'] += goods_special_temp
        production['rogues_units'] = rogues_temp
        production['fast_units'] = units['Fast']
        production['heavy_units'] = units['Heavy']
        production['ranged_units'] = units['Ranged']
        production['artillery_units'] = units['Artillery']
        production['light_units'] = units['Light']
        production['units_amount'] = sum(units.values()) + rogues_temp
        production['units_type'] = ", ".join([f"{k}: {v:.2f}" for k, v in units.items() if v > 0]) + (f", Rogues: {rogues_temp:.2f}" if rogues_temp > 0 else "")

        production['next_age_fast_units'] = next_age_units['Fast']
        production['next_age_heavy_units'] = next_age_units['Heavy']
        production['next_age_ranged_units'] = next_age_units['Ranged']
        production['next_age_artillery_units'] = next_age_units['Artillery']
        production['next_age_light_units'] = next_age_units['Light']
        production['next_age_units_amount'] = sum(next_age_units.values())
        production['next_age_units_type'] = ", ".join([f"{k}: {v:.2f}" for k, v in next_age_units.items() if v > 0])

        production['other_items'] = sorted(list(set(other_items_temp))) # Unique and sorted

        # Round floats at the end
        for k, v in production.items():
            if isinstance(v, float):
                production[k] = round(v, 2)

        return production

    @staticmethod
    def _get_boost_data(components: Dict, era_key: str) -> Dict[str, float]:
        """Calculate boost values directly for a specific era."""
        boosts = {
            "Red Attack": 0.0, "Red Defense": 0.0, "Red GBG Attack": 0.0, "Red GBG Defense": 0.0,
            "Red GE Attack": 0.0, "Red GE Defense": 0.0, "Red QI Attack": 0.0, "Red QI Defense": 0.0,
            "Blue Attack": 0.0, "Blue Defense": 0.0, "Blue GBG Attack": 0.0, "Blue GBG Defense": 0.0,
            "Blue GE Attack": 0.0, "Blue GE Defense": 0.0, "Blue QI Attack": 0.0, "Blue QI Defense": 0.0,
            "Coin %": 0.0, "QI Coin %": 0.0, "QI Coin at start": 0.0, "Supplies %": 0.0,
            "QI Supplies %": 0.0, "QI Supplies at start": 0.0, "QI Goods at start": 0.0,
            "QI Units at start": 0.0, "QA per hour": 0.0, "FP boost": 0.0, "Guild Goods Production %": 0.0,
            "Special Goods Production %": 0.0, "Medal Boost": 0.0, "Goods Boost": 0.0
        }
        boost_map = {
            ('att_boost_attacker', 'all'): ["Red Attack"], ('def_boost_attacker', 'all'): ["Red Defense"],
            ('att_boost_attacker', 'battleground'): ["Red GBG Attack"], ('def_boost_attacker', 'battleground'): ["Red GBG Defense"],
            ('att_boost_attacker', 'guild_expedition'): ["Red GE Attack"], ('def_boost_attacker', 'guild_expedition'): ["Red GE Defense"],
            ('att_boost_attacker', 'guild_raids'): ["Red QI Attack"], ('def_boost_attacker', 'guild_raids'): ["Red QI Defense"],
            ('att_boost_defender', 'all'): ["Blue Attack"], ('def_boost_defender', 'all'): ["Blue Defense"],
            ('att_boost_defender', 'battleground'): ["Blue GBG Attack"], ('def_boost_defender', 'battleground'): ["Blue GBG Defense"],
            ('att_boost_defender', 'guild_expedition'): ["Blue GE Attack"], ('def_boost_defender', 'guild_expedition'): ["Blue GE Defense"],
            ('att_boost_defender', 'guild_raids'): ["Blue QI Attack"], ('def_boost_defender', 'guild_raids'): ["Blue QI Defense"],
            ('att_def_boost_attacker', 'all'): ["Red Attack", "Red Defense"],
            ('att_def_boost_attacker', 'battleground'): ["Red GBG Attack", "Red GBG Defense"],
            ('att_def_boost_attacker', 'guild_expedition'): ["Red GE Attack", "Red GE Defense"],
            ('att_def_boost_attacker', 'guild_raids'): ["Red QI Attack", "Red QI Defense"],
            ('att_def_boost_defender', 'all'): ["Blue Attack", "Blue Defense"],
            ('att_def_boost_defender', 'battleground'): ["Blue GBG Attack", "Blue GBG Defense"],
            ('att_def_boost_defender', 'guild_expedition'): ["Blue GE Attack", "Blue GE Defense"],
            ('att_def_boost_defender', 'guild_raids'): ["Blue QI Attack", "Blue QI Defense"],
            ('att_def_boost_attacker_defender', 'all'): ["Red Attack", "Red Defense", "Blue Attack", "Blue Defense"],
            ('att_def_boost_attacker_defender', 'battleground'): ["Red GBG Attack", "Red GBG Defense", "Blue GBG Attack", "Blue GBG Defense"],
            ('att_def_boost_attacker_defender', 'guild_expedition'): ["Red GE Attack", "Red GE Defense", "Blue GE Attack", "Blue GE Defense"],
            ('att_def_boost_attacker_defender', 'guild_raids'): ["Red QI Attack", "Red QI Defense", "Blue QI Attack", "Blue QI Defense"],
            ('coin_production', 'all'): ["Coin %"], ('supply_production', 'all'): ["Supplies %"],
            ('guild_raids_coins_production', 'all'): ["QI Coin %"], ('guild_raids_coins_start', 'all'): ["QI Coin at start"],
            ('guild_raids_supplies_production', 'all'): ["QI Supplies %"], ('guild_raids_supplies_start', 'all'): ["QI Supplies at start"],
            ('guild_raids_goods_start', 'all'): ["QI Goods at start"], ('guild_raids_units_start', 'all'): ["QI Units at start"],
            ('guild_raids_action_points_collection', 'all'): ["QA per hour"],
            ('forge_points_production', 'all'): ["FP boost"], ('guild_goods_production', 'all'): ["Guild Goods Production %"],
            ('special_goods_production', 'all'): ["Special Goods Production %"],
            ('medal_production', 'all'): ["Medal Boost"], ('goods_production', 'all'): ["Goods Boost"]
        }

        for component_key in [era_key, 'AllAge']:
            component_data = components.get(component_key, {})
            boost_comp = component_data.get('boosts', {})
            if not boost_comp: continue

            for boost in boost_comp.get('boosts', []):
                 boost_type = boost.get('type')
                 target = boost.get('targetedFeature')
                 value = float(boost.get('value', 0))
                 map_key = (boost_type, target)

                 if map_key in boost_map:
                     final_keys = boost_map[map_key]
                     for final_key in final_keys:
                         if final_key in boosts:
                             boosts[final_key] += value
                         else:
                              logger.warning(f"Boost key '{final_key}' derived from map but not in boosts dict structure.")

        # Round floats
        for k, v in boosts.items():
            boosts[k] = round(v, 2)

        return boosts

    def load_data(self):
        """Load building data from JSON and parse directly into a list of dictionaries."""
        try:
            if not self.file_path.startswith("https"):
                logger.info("Loading JSON File")
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    raw_building_data = json.load(f)
            else:
                logger.info("Loading Github URL")
                raw_building_data = json.loads(r.get(self.file_path).content)

            with open(os.path.join(ASSETS_PATH, 'event_tags.json'), 'r', encoding='utf-8') as f:
                event_tags = json.load(f)
                
            with open(os.path.join(ASSETS_PATH, 'event_building_tag_exceptions.json'), 'r', encoding='utf-8') as f:
                event_building_tag_exceptions = json.load(f)
            
            self.building_data_list = [] # Reset
            processed_count = 0
            skipped_asset_id = 0
            no_components = 0
            error_count = 0
            
            for building_entry in raw_building_data:
                building_id = building_entry.get('id')
                # Filter by asset ID
                if not building_id.startswith(('W_')): # Adjust filter as needed
                    skipped_asset_id += 1
                    continue
                building_name = building_entry.get('name', 'Unknown')
                building_event_tag = None
                if building_id in event_building_tag_exceptions.keys():
                    building_event_tag = event_building_tag_exceptions[building_id]
                else:
                    for tag in event_tags.keys():
                        if tag in building_id and tag not in ["COP", "Expedition"]:
                            if tag != "GBG":
                                for v in [18,19,20,21,22,23,24,25,26,27,28,29,30]:
                                    if f"{v}" in building_id:
                                        building_event_tag = event_tags[tag] + f" 20{v}"
                                        break
                            elif tag == "GBG":
                                for v in [23,24,25,26,27,28,29,30]:
                                    if f"{v}" in building_id:
                                        building_event_tag = event_tags[tag] + f" 20{v}"
                                        break
                        elif tag in building_id and tag in ["Expedition", "COP"]:
                            building_event_tag = event_tags[tag]
                            break
                    if not building_event_tag:
                        building_event_tag = building_id

                components = building_entry.get('components')
                if not components or not isinstance(components, dict):
                     logger.warning(f"Building {building_name} ({building_id}) has no components dict. Skipping.")
                     no_components += 1
                     continue

                # --- Pre-calculate common 'AllAge' data once per building ---
                try:
                     width, height, size_str, sq_avg, needs_road = self._calculate_size_data(components)
                     limited_str = self._check_limitations(components)
                     ally_room_str = self._get_ally_room(components)
                except Exception as e:
                    logger.error(f"Error processing common data for {building_name} ({building_id}): {e}")
                    error_count += 1
                    continue # Skip building if basic data fails

                # Iterate through eras found in this building's components
                era_instance_created = False
                for era_key in components.keys():
                    if era_key == 'AllAge': continue # Skip the generic 'AllAge' component

                    try:
                        # Get era-specific data
                        pop, happiness = self._get_pop_happiness(components, era_key)
                        production_data = self._get_production_data(components, era_key, building_name)
                        boost_data = self._get_boost_data(components, era_key)

                        # Combine all data into a single dictionary
                        building_dict = {
                            "id": building_id,
                            "name": building_name,
                            "Event": building_event_tag,
                            "Era": era_key, # Store raw key for later translation/grouping
                            "x": width,
                            "y": height,
                            "size": size_str,
                            "Nbr of squares (Avg)": sq_avg,
                            "Road": needs_road,
                            "Limited": limited_str,
                            "Ally room": ally_room_str,
                            "Population": pop,
                            "Happiness": happiness,
                            **production_data, # Unpack production dict
                            **boost_data, # Unpack boost dict
                            "Other productions": ', '.join(production_data.get('other_items',[])) # Extract other items
                        }
                        
                        # Remove the intermediate 'other_items' key if present
                        # building_dict.pop('other_items', None)

                        self.building_data_list.append(building_dict)
                        processed_count += 1
                        era_instance_created = True

                    except Exception as e:
                        logger.error(f"Error processing era '{era_key}' for {building_name} ({building_id}): {e}", exc_info=False) # exc_info=False keeps log cleaner
                        error_count += 1
                        # Continue to next era even if one fails

                # Log if a building entry didn't yield any era-specific instances
                if not era_instance_created and error_count == 0: # Only log if no errors occurred for this building
                     logger.debug(f"Building {building_name} ({building_id}) had components but no specific era instances created (only AllAge?). Components: {list(components.keys())}")

            logger.info(f"Processed {processed_count} building-era dictionaries.")
            if skipped_asset_id > 0: logger.info(f"Skipped {skipped_asset_id} entries due to asset ID.")
            if no_components > 0: logger.info(f"Skipped {no_components} entries due to missing components.")
            if error_count > 0: logger.warning(f"Encountered {error_count} errors during individual building/era processing.")

        except FileNotFoundError:
            logger.error(f"Metadata file not found: {self.file_path}")
            raise # Reraise critical error
        except json.JSONDecodeError as e:
             logger.error(f"Invalid JSON in metadata file {self.file_path}: {e}")
             raise # Reraise critical error
        except Exception as e:
            logger.error(f"Unexpected error during data loading: {e}", exc_info=True)
            raise # Reraise critical error

    def analyze(self):
        """Create DataFrame from the list of building dictionaries and optimize dtypes."""
        if not self.building_data_list:
            logger.warning("No building data loaded to analyze.")
            self.df = pd.DataFrame() # Ensure df is an empty DataFrame
            return

        try:
            self.df = pd.DataFrame(self.building_data_list)
            logger.info(f"DataFrame created with shape: {self.df.shape}")
            
            # --- Optimize Dtypes ---
            logger.info("Optimizing DataFrame dtypes...")
            for col in ['Era', 'Limited', 'Road', 'Ally room']:
                if col in self.df.columns:
                    try:
                        if col == 'Road': # Handle boolean specifically
                           self.df[col] = self.df[col].astype(bool)
                        else:
                           self.df[col] = self.df[col].astype('category')
                        logger.debug(f"Converted column '{col}' to {self.df[col].dtype} dtype.")
                    except Exception as e:
                         logger.warning(f"Could not convert column '{col}' to category/bool: {e}")

            # Optional: Convert numeric types more specifically
            # float_cols = self.df.select_dtypes(include=['float64']).columns
            # self.df[float_cols] = self.df[float_cols].astype('float32')
            # logger.debug("Converted float64 columns to float32.")

            # Ensure numeric columns that should be numeric are
            numeric_cols_to_check = [
                 col for col in self.df.columns
                 if col not in ['id', 'Event', 'name', 'Era', 'size', 'Road', 'Limited', 'Ally room', 'Unit type', 'Next Age Unit type', 'Other productions']
            ]
            for col in numeric_cols_to_check:
                 if col in self.df.columns:
                    try:
                         # errors='coerce' will turn non-numeric values into NaN
                         self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
                         # Optionally fill NaN introduced by coercion if needed, e.g., self.df[col].fillna(0, inplace=True)
                    except Exception as e:
                         logger.warning(f"Could not convert column '{col}' to numeric: {e}")


            logger.info("DataFrame analysis (creation and dtype optimization) complete.")

        except Exception as e:
            logger.error(f"Error creating or optimizing DataFrame: {e}", exc_info=True)
            self.df = pd.DataFrame() # Reset to empty on error
            raise # Critical error

    def export_to_excel(self, filename: str = 'building_analysis.xlsx'):
        """Export analysis results to Excel."""
        if self.df is not None and not self.df.empty:
            try:
                self.df.to_excel(filename, index=False)
                logger.info(f"Data exported to {filename}")
            except Exception as e:
                logger.error(f"Failed to export to Excel: {e}")
        else:
            logger.warning("No DataFrame available to export to Excel.")

    def export_to_database(self, db_path: str = DB_PATH):
        """Export analysis results to SQLite database."""
        if self.df is None or self.df.empty:
            logger.warning("No data to export to database")
            return
        try:
            with sqlite3.connect(db_path) as conn:
                 # Check/add columns logic might need adjustment if dtypes changed significantly
                 try:
                    existing_table = pd.read_sql("SELECT * FROM buildings LIMIT 0", conn)
                    existing_cols = existing_table.columns
                    for col in self.df.columns:
                        if col not in existing_cols:
                            pd_dtype = self.df[col].dtype
                            sql_type = 'TEXT' # Default
                            if pd.api.types.is_integer_dtype(pd_dtype): sql_type = 'INTEGER'
                            elif pd.api.types.is_float_dtype(pd_dtype): sql_type = 'REAL'
                            elif pd.api.types.is_bool_dtype(pd_dtype): sql_type = 'INTEGER' # SQLite uses 0/1

                            logger.info(f"Adding missing column '{col}' with type '{sql_type}' to database table.")
                            alter_query = f'ALTER TABLE buildings ADD COLUMN "{col}" {sql_type}' # Quote column name
                            conn.execute(alter_query)
                 except sqlite3.OperationalError as oe:
                      if "no such table" not in str(oe).lower():
                           logger.warning(f"SQLite operational error checking columns: {oe}")
                 except Exception as e:
                      logger.error(f"Error checking/adding columns in DB: {e}")

                 self.df.to_sql('buildings', conn, if_exists='replace', index=False)
                 logger.info(f"Data exported to database: {db_path}")
        except Exception as e:
            logger.error(f"Error exporting to database: {str(e)}")
            # Do not raise here

# --- Data Loading Function (using BuildingAnalyzer) ---
@st.cache_data
def load_and_process_data(metadata_file_path: str) -> pd.DataFrame:
    """Loads data from JSON, analyzes buildings using BuildingAnalyzer, and returns a DataFrame."""
    logger.info(f"Executing load_and_process_data from: {metadata_file_path}")
    if not metadata_file_path.startswith("https"):
        if not os.path.exists(metadata_file_path):
            st.error(f"Metadata file not found at: {metadata_file_path}")
            logger.error(f"Metadata file not found at: {metadata_file_path}")
            return pd.DataFrame() # Return empty DataFrame

    try:
        analyzer = BuildingAnalyzer(metadata_file_path)
        analyzer.load_data() # Populates analyzer.building_data_list
        analyzer.analyze() # Creates and optimizes analyzer.df
        logger.info("Data loading and analysis complete in load_and_process_data.")
        # Optional: Export to DB here if it MUST happen on data load/refresh
        # try:
        #     analyzer.export_to_database(DB_PATH)
        # except Exception as e:
        #     st.error(f"Failed to export data to database: {e}")
        #     logger.error(f"Failed to export data to database: {e}")
        return analyzer.df if analyzer.df is not None else pd.DataFrame()
    except Exception as e:
        logger.error(f"Error during data processing pipeline in load_and_process_data: {e}", exc_info=True)
        st.error(f"Error processing data: {str(e)}. Check logs.")
        # Depending on severity, might want to return empty df or raise
        return pd.DataFrame() 