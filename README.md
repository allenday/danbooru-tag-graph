# Danbooru Tag Graph

A NetworkX-based graph system for efficiently managing Danbooru tag relationships including implications, aliases, and deprecated status.

## Features

- **High-performance graph operations** using NetworkX
- **Tag relationship management** (implications and aliases)
- **Deprecated tag tracking**
- **Efficient serialization** with pickle
- **Transitive relationship queries**
- **Batch operations** for optimal performance

## Installation

```bash
pip install danbooru-tag-graph
```

## Quick Start

```python
from danbooru_tag_graph import DanbooruTagGraph

# Create a new graph
graph = DanbooruTagGraph()

# Add tags
graph.add_tag("cat", is_deprecated=False, fetched=True)
graph.add_tag("animal", is_deprecated=False, fetched=True)
graph.add_tag("feline", is_deprecated=False, fetched=True)

# Add relationships
graph.add_implication("cat", "animal")  # cat implies animal
graph.add_alias("cat", "feline")        # cat and feline are aliases

# Query relationships
implications = graph.get_implications("cat")
aliases = graph.get_aliases("cat")
transitive = graph.get_transitive_implications("cat")

# Expand tags with frequencies
expanded_tags, frequencies = graph.expand_tags(["cat"])
print(f"Expanded: {expanded_tags}")
print(f"Frequencies: {frequencies}")

# Save/load graph
graph.save_graph("my_tags.pickle")
new_graph = DanbooruTagGraph("my_tags.pickle")
```

## Graph Structure

The tag graph uses NetworkX's `MultiDiGraph` with:

- **Nodes**: Individual tags with metadata (deprecated status, fetched status, etc.)
- **Edges**: Two types:
  1. `'implication'`: Directed edges from antecedent to consequent tags
  2. `'alias'`: Bidirectional edges between alias tags

## Performance Benefits

- **Single file load** vs thousands of individual files
- **In-memory graph operations** instead of repeated file I/O
- **Batch relationship queries** and transitive closure pre-computation
- **Efficient serialization** with pickle

## API Reference

### DanbooruTagGraph

#### Core Methods

- `add_tag(tag, is_deprecated=False, fetched=False, **metadata)` - Add a tag node
- `add_implication(antecedent, consequent)` - Add implication relationship
- `add_alias(tag1, tag2)` - Add alias relationship
- `is_tag_deprecated(tag)` - Check if tag is deprecated
- `mark_tag_fetched(tag)` - Mark tag as having relationships fetched
- `is_tag_fetched(tag)` - Check if tag relationships are fetched

#### Query Methods

- `get_implications(tag, include_deprecated=False)` - Get direct implications
- `get_aliases(tag, include_deprecated=False)` - Get direct aliases
- `get_transitive_implications(tag, include_deprecated=False)` - Get all transitive implications
- `get_alias_group(tag, include_deprecated=False)` - Get complete alias group
- `expand_tags(tags, include_deprecated=False)` - Expand tags with frequencies

#### Persistence Methods

- `load_graph(cache_file)` - Load graph from pickle file
- `save_graph(cache_file=None)` - Save graph to pickle file
- `auto_save()` - Save if graph has been modified

#### Utility Methods

- `stats()` - Get graph statistics
- `get_unfetched_tags(tags)` - Get list of tags needing data fetch
- `import_from_json_cache(cache_dir)` - Import from old JSON cache format

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.