# 🧮 Math Knowledge Base - Graphic User Interface

## 🎯 Overview

The Math Knowledge Base now features a modern, comprehensive web-based GUI built with **Streamlit**. This interface provides an intuitive way to manage mathematical concepts, relationships, and knowledge graphs.

## 🚀 Quick Start

### Option 1: Using the Launcher (Recommended)
```bash
# Make sure you're in your virtual environment
source mathdbmongo/bin/activate

# Run the GUI launcher
python run_gui.py
```

### Option 2: Using Make
```bash
# Start MongoDB first
make start

# Launch the GUI
make gui
```

### Option 3: Direct Streamlit
```bash
streamlit run editor/editor_streamlit.py
```

The GUI will automatically open in your default web browser at `http://localhost:8501`.

## 📱 Interface Features

### 🏠 Dashboard
- **Real-time Statistics**: View total concepts, relations, sources, and categories
- **Recent Concepts**: See the latest added mathematical concepts
- **Quick Stats**: Visual charts showing concept type distribution and top categories
- **Database Status**: Monitor connection health

### ➕ Add Concept
Comprehensive form for adding new mathematical concepts with:

- **Basic Information**: ID, title, type, categories, source
- **LaTeX Content Editor**: Rich text area for mathematical content
- **Algorithm Support**: Special fields for step-by-step algorithms
- **Reference Management**: Complete bibliographic information
- **Teaching Context**: Educational level and formality settings
- **Technical Metadata**: Formal notation, proofs, prerequisites
- **Real-time Validation**: Form validation and error handling

### 📚 Browse Concepts
- **Advanced Filtering**: Filter by type, source, and search terms
- **Interactive Cards**: Expandable concept cards with full details
- **Quick Actions**: Export to PDF, view relations, delete concepts
- **LaTeX Preview**: Syntax-highlighted LaTeX content display

### 🔗 Manage Relations
- **Add Relations**: Create connections between concepts
- **Relation Types**: Support for all semantic relationship types
- **Visual Management**: Browse and manage existing relations
- **Bulk Operations**: Efficient relation management

### 📊 Knowledge Graph
- **Interactive Visualization**: Dynamic network graphs using Pyvis
- **Configurable Filters**: Select sources, concept types, and relation types
- **Depth Control**: Adjust graph exploration depth
- **Export Options**: Download interactive HTML graphs
- **Statistics**: Node and edge counts with source breakdown

### 📤 Export
- **Multiple Formats**: PDF and LaTeX export options
- **Bulk Export**: Export entire sources or concept types
- **Custom Output**: Specify output directories
- **Progress Tracking**: Real-time export progress

### ⚙️ Settings
- **Database Status**: Connection monitoring and statistics
- **System Information**: Application version and details
- **Maintenance Tools**: Index rebuilding and data clearing
- **Configuration**: Database and application settings

## 🎨 UI Design Features

### Modern Styling
- **Responsive Layout**: Works on desktop and tablet devices
- **Custom CSS**: Professional mathematical theme
- **Color Coding**: Different colors for concept types and relations
- **Interactive Elements**: Hover effects and smooth transitions

### User Experience
- **Intuitive Navigation**: Sidebar-based navigation
- **Form Validation**: Real-time error checking and feedback
- **Progress Indicators**: Loading states and progress bars
- **Success Feedback**: Confirmation messages and animations

### Accessibility
- **Keyboard Navigation**: Full keyboard support
- **Screen Reader Friendly**: Proper ARIA labels and semantic HTML
- **High Contrast**: Readable color schemes
- **Responsive Design**: Adapts to different screen sizes

## 🔧 Technical Features

### Database Integration
- **MongoDB Connection**: Seamless integration with existing database
- **Caching**: Optimized database queries with Streamlit caching
- **Error Handling**: Graceful handling of connection issues
- **Real-time Updates**: Live data synchronization

### LaTeX Support
- **Syntax Highlighting**: Colored LaTeX code display
- **Preview Mode**: Real-time LaTeX rendering (where supported)
- **Export Integration**: Direct PDF generation from LaTeX content
- **Template Support**: Custom LaTeX templates and styles

### Knowledge Graph
- **Interactive Networks**: Zoom, pan, and click interactions
- **Dynamic Filtering**: Real-time graph updates based on filters
- **Export Options**: HTML, PNG, and other formats
- **Performance Optimized**: Efficient rendering for large graphs

## 📋 Usage Examples

### Adding a New Theorem
1. Navigate to "➕ Add Concept"
2. Select "teorema" as the concept type
3. Fill in the basic information (ID, title, categories)
4. Write the theorem statement in LaTeX
5. Add proof if available
6. Include reference information
7. Set teaching context and technical metadata
8. Click "Save Concept"

### Creating a Knowledge Graph
1. Go to "📊 Knowledge Graph"
2. Select the sources you want to include
3. Choose concept types (e.g., definitions, theorems)
4. Select relation types (e.g., implies, derives from)
5. Set the maximum depth for exploration
6. Click "Generate Graph"
7. Interact with the graph or download it

### Exporting Concepts
1. Navigate to "📤 Export"
2. Select a source and concept type
3. Choose export format (PDF or LaTeX)
4. Specify output directory
5. Click "Export"
6. Monitor progress and download results

## 🛠️ Troubleshooting

### Common Issues

**Database Connection Failed**
- Ensure MongoDB is running: `sudo systemctl start mongod`
- Check if the virtual environment is activated
- Verify MongoDB is accessible on localhost:27017

**Dependencies Missing**
- Install requirements: `pip install -r requirements.txt`
- Update Streamlit: `pip install --upgrade streamlit`

**GUI Not Loading**
- Check if port 8501 is available
- Try a different port: `streamlit run editor/editor_streamlit.py --server.port 8502`
- Clear browser cache and cookies

**Export Failures**
- Ensure LaTeX is installed on your system
- Check write permissions for output directories
- Verify LaTeX content is valid

### Performance Tips
- Use filters to limit data in large databases
- Close unused browser tabs to free memory
- Restart the application if it becomes slow
- Consider using smaller graph depths for large datasets

## 🔮 Future Enhancements

### Planned Features
- **Collaborative Editing**: Multi-user support with real-time collaboration
- **Advanced Search**: Full-text search with mathematical notation
- **Version Control**: Track changes and revert to previous versions
- **Plugin System**: Extensible architecture for custom features
- **Mobile App**: Native mobile application
- **API Integration**: RESTful API for external integrations

### Customization Options
- **Theme Customization**: User-defined color schemes and layouts
- **Workflow Automation**: Custom export and import workflows
- **Template System**: Customizable LaTeX and HTML templates
- **Plugin Development**: Framework for third-party extensions

## 📞 Support

For issues, questions, or feature requests:
- Check the main project README for general information
- Review the troubleshooting section above
- Open an issue on the project repository
- Contact the development team

---

**Happy Mathematical Knowledge Management! 🧮✨** 