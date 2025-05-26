# FoE Building Analyzer

A comprehensive web application for analyzing and comparing buildings from Forge of Empires. This tool helps players make informed decisions about which buildings to place in their cities by providing detailed efficiency calculations and comparisons.

## 🌟 Features

### Core Functionality
- **Building Database**: Complete database of Forge of Empires buildings with detailed statistics
- **Multi-Language Support**: Available in English and French with full translation support
- **Era Filtering**: Filter buildings by specific eras (Bronze Age to Space Age: Space Hub)
- **Event Filtering**: Filter buildings by events or view all buildings
- **Search Functionality**: Search buildings by name
- **Export Options**: Export filtered data as CSV or JSON

### Advanced Analysis
- **Weighted Efficiency Calculator**: Calculate building efficiency based on your personal preferences
- **City Context Integration**: Input your city's production to accurately value boost buildings
- **Direct Weighted Sum**: No arbitrary normalization - uses real production values
- **Boost Integration**: Automatically converts boost percentages to equivalent production values
- **Per-Square Analysis**: View all metrics normalized per building tile

### User Interface
- **Interactive Data Grid**: Powered by AG-Grid with sorting, filtering, and pagination
- **Icon Support**: Visual building icons in column headers (optional)
- **Heatmap Visualization**: Color-coded efficiency visualization
- **Responsive Design**: Works on desktop and mobile devices
- **Column Grouping**: Organize data by categories (Production, Military, Boosts, etc.)

### Building Categories
- **Basic Info**: Size, population, happiness, road requirements
- **Production**: Coins, supplies, goods, forge points, medals
- **Military Units**: All unit types including next-age units
- **Army Bonuses**: Attack/defense bonuses for different game modes (GBG, GE, QI)
- **Boost Buildings**: FP boost, goods boost, guild goods boost, special goods boost
- **Consumables**: Various kits and instant finishes
- **Quantum Incursions**: QI-specific bonuses and starting resources

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Setup
1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd FoEBuildingDB
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   streamlit run app.py
   ```

4. **Open your browser** and navigate to `http://localhost:8501`

### Dependencies
- `streamlit`: Web application framework
- `pandas`: Data manipulation and analysis
- `streamlit-aggrid`: Interactive data grid component
- `Pillow`: Image processing for icons
- `requests`: HTTP library for data fetching

## 📖 Usage

### Basic Usage
1. **Select Language**: Choose between English and French
2. **Filter Data**: Use the sidebar to filter by era, event, or building name
3. **Choose Columns**: Select which information groups to display
4. **View Results**: Browse the interactive table with building data

### Efficiency Analysis
1. **Navigate to Weights Tab**: Click on the "Weights" tab
2. **Set City Context**: Enter your daily production values for accurate boost calculations
3. **Set Point Values**: Assign point values to different production types
4. **View Results**: Return to the Home tab to see calculated efficiency scores

### City Context Fields
- **Daily FP Production**: Your total daily Forge Points from all sources
- **Daily Goods Production**: Current, previous, and next age goods production
- **Daily Guild Goods Production**: Your guild goods production
- **Daily Special Goods Production**: Your special goods production

### Efficiency Calculation
The efficiency system uses a **direct weighted sum** approach:

1. **Point Assignment**: You assign point values to each production type (e.g., 1 FP = 10 points)
2. **Boost Integration**: Boost buildings are automatically converted to equivalent production
3. **Total Score**: All weighted production values are summed
4. **Efficiency Score**: Total score divided by building size (including road requirements)

## 🏗️ Project Structure

```
FoEBuildingDB/
├── app.py                 # Main Streamlit application
├── config.py             # Configuration and constants
├── data_loader.py        # Data loading and processing
├── calculations.py       # Efficiency calculations
├── translations.py       # Multi-language support
├── ui_components.py      # UI components and AG-Grid configuration
├── assets/               # Icons and static files
│   ├── icons/           # Building icons
│   ├── event_tags.json  # Event classification data
│   └── event_building_tag_exceptions.json
├── translations/         # Translation files
│   ├── en/              # English translations
│   │   ├── ui.json
│   │   ├── columns.json
│   │   ├── building_names.json
│   │   ├── events.json
│   │   └── eras.json
│   └── fr/              # French translations
│       ├── ui.json
│       ├── columns.json
│       ├── building_names.json
│       ├── events.json
│       └── eras.json
└── requirements.txt      # Python dependencies
```

## 🔧 Technical Details

### Data Source
- Building data is fetched from the official FoE Buildings Database repository
- Data includes all building statistics, production values, and metadata
- Automatic parsing of complex reward structures and random productions

### Calculation Engine
- **Direct Weighted Sum**: No normalization artifacts - preserves real production differences
- **Boost Conversion**: Automatically converts percentage boosts to equivalent production
- **Context Awareness**: Boost values scale with your actual city production
- **Multi-Era Support**: Handles special goods conversion for different eras

### Performance Optimizations
- **Caching**: Streamlit caching for data loading and processing
- **Efficient Data Structures**: Optimized pandas DataFrames with appropriate dtypes
- **Icon Caching**: LRU cache for icon loading and base64 conversion
- **Translation Caching**: Pre-loaded translation dictionaries

## 🌍 Internationalization

The application supports multiple languages through a comprehensive translation system:

- **UI Elements**: All interface text is translatable
- **Building Names**: Building names in multiple languages
- **Column Headers**: Data table headers in multiple languages
- **Events and Eras**: Game-specific terminology translations
- **Help Text**: Contextual help and tooltips

### Adding New Languages
1. Create new translation files in `translations/<language_code>/`
2. Add the language to `LANGUAGES` in `translations.py`
3. Translate all required keys following the existing structure

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

### Translation Contributions

Help us expand language support by contributing translations:
1. Copy the English translation files (aside from building_names.json, I'm working on a different way to handle it)
2. Translate all text while preserving JSON structure
3. Test the translations in the application
4. Submit a pull request

## 📊 Data Accuracy

- All random productions are calculated as daily averages
- Boost buildings are converted using your actual city context
- Special goods handling varies by era (automatically managed)
- Production values include drop chances and probability calculations

## 🐛 Known Issues

- Column auto-sizing is sometimes not working
- Unique buildings are not differentiated from other buildings
- Large datasets may experience slower loading times
- Mobile interface may require horizontal scrolling for full data view
- Translation of building names is not always correct, as when not available in the database, the english name is used instead. It needs to be manually translated. It also needs a rework so that it is handled more smoothly. I'm working on it.

## 📝 License

This project is open source. Please check the repository for specific license terms.

## 🙏 Acknowledgments

- Forge of Empires community for building data and feedback
- Streamlit team for the excellent web framework
- AG-Grid team for the powerful data grid component
- Contributors and translators who help improve the application

## 📞 Support

For support, feature requests, or bug reports, please use the GitHub issue tracker or contact the development team.

---

**Note**: This application is not affiliated with InnoGames or Forge of Empires. It is a community tool created by players for players. 