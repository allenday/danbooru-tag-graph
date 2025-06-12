"""
Danbooru Tag Graph

A NetworkX-based graph system for efficiently managing Danbooru tag relationships
including implications, aliases, and deprecated status.

Future package: danbooru-tag-graph
"""

import os
import json
import pickle
import logging
from typing import Dict, List, Set, Optional, Tuple, Union
from collections import defaultdict
import networkx as nx

logger = logging.getLogger(__name__)


class DanbooruTagGraph:
    """
    A NetworkX-based graph for efficiently managing Danbooru tag relationships.
    
    This class provides high-performance caching and querying of tag implications,
    aliases, and deprecated status using a directed graph structure.
    
    Graph Structure:
    - Nodes: Individual tags with metadata (deprecated status, etc.)
    - Edges: Two types:
      1. 'implication': Directed edges from antecedent to consequent tags
      2. 'alias': Bidirectional edges between alias tags
    
    Performance Benefits:
    - Single file load vs thousands of individual files
    - In-memory graph operations
    - Batch relationship queries
    - Transitive closure pre-computation
    """
    
    def __init__(self, cache_file: Optional[str] = None):
        """
        Initialize the Danbooru tag graph.
        
        Args:
            cache_file: Path to the serialized graph cache file
        """
        self.graph = nx.MultiDiGraph()  # Allows multiple edge types between nodes
        self.cache_file = cache_file
        self._dirty = False  # Track if graph needs saving
        
        # Load existing graph if cache file exists
        if cache_file and os.path.exists(cache_file):
            self.load_graph(cache_file)
    
    def add_tag(self, tag: str, is_deprecated: bool = False, fetched: bool = False, **metadata) -> None:
        """
        Add a tag node to the graph with metadata.
        
        Args:
            tag: The tag name
            is_deprecated: Whether the tag is deprecated
            fetched: Whether this tag's relationships have been fetched from API
            **metadata: Additional tag metadata
        """
        self.graph.add_node(tag, deprecated=is_deprecated, fetched=fetched, **metadata)
        self._dirty = True
    
    def add_implication(self, antecedent: str, consequent: str) -> None:
        """
        Add an implication relationship: antecedent -> consequent.
        
        Args:
            antecedent: The tag that implies another
            consequent: The tag that is implied
        """
        # Ensure both nodes exist
        if not self.graph.has_node(antecedent):
            self.add_tag(antecedent)
        if not self.graph.has_node(consequent):
            self.add_tag(consequent)
        
        # Add implication edge
        self.graph.add_edge(antecedent, consequent, edge_type='implication')
        self._dirty = True
    
    def add_alias(self, tag1: str, tag2: str) -> None:
        """
        Add an alias relationship between two tags (bidirectional).
        
        Args:
            tag1: First tag in alias relationship
            tag2: Second tag in alias relationship
        """
        # Ensure both nodes exist
        if not self.graph.has_node(tag1):
            self.add_tag(tag1)
        if not self.graph.has_node(tag2):
            self.add_tag(tag2)
        
        # Add bidirectional alias edges
        self.graph.add_edge(tag1, tag2, edge_type='alias')
        self.graph.add_edge(tag2, tag1, edge_type='alias')
        self._dirty = True
    
    def is_tag_deprecated(self, tag: str) -> bool:
        """
        Check if a tag is deprecated.
        
        Args:
            tag: The tag to check
            
        Returns:
            True if deprecated, False otherwise
        """
        if not self.graph.has_node(tag):
            return False
        return self.graph.nodes[tag].get('deprecated', False)
    
    def get_implications(self, tag: str, include_deprecated: bool = False) -> List[str]:
        """
        Get all tags that this tag implies.
        
        Args:
            tag: The tag to get implications for
            include_deprecated: Whether to include deprecated implied tags
            
        Returns:
            List of implied tag names
        """
        if not self.graph.has_node(tag):
            return []
        
        implications = []
        for successor in self.graph.successors(tag):
            # Check if edge is an implication
            edge_data = self.graph.get_edge_data(tag, successor)
            for edge in edge_data.values():
                if edge.get('edge_type') == 'implication':
                    if include_deprecated or not self.is_tag_deprecated(successor):
                        implications.append(successor)
                    break
        
        return implications
    
    def get_aliases(self, tag: str, include_deprecated: bool = False) -> List[str]:
        """
        Get all aliases for this tag.
        
        Args:
            tag: The tag to get aliases for
            include_deprecated: Whether to include deprecated aliases
            
        Returns:
            List of alias tag names
        """
        if not self.graph.has_node(tag):
            return []
        
        aliases = []
        # Check both successors and predecessors for alias edges
        neighbors = set(self.graph.successors(tag)) | set(self.graph.predecessors(tag))
        
        for neighbor in neighbors:
            # Check for alias edges in both directions
            edge_data_out = self.graph.get_edge_data(tag, neighbor, default={})
            edge_data_in = self.graph.get_edge_data(neighbor, tag, default={})
            
            for edge_dict in [edge_data_out, edge_data_in]:
                for edge in edge_dict.values():
                    if edge.get('edge_type') == 'alias':
                        if include_deprecated or not self.is_tag_deprecated(neighbor):
                            aliases.append(neighbor)
                        break
        
        return list(set(aliases))  # Remove duplicates
    
    def get_transitive_implications(self, tag: str, include_deprecated: bool = False) -> Set[str]:
        """
        Get all tags implied by this tag transitively (following the implication chain).
        
        Args:
            tag: The starting tag
            include_deprecated: Whether to include deprecated tags
            
        Returns:
            Set of all transitively implied tag names
        """
        if not self.graph.has_node(tag):
            return set()
        
        # Create a subgraph with only implication edges
        impl_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            if data.get('edge_type') == 'implication':
                if include_deprecated or (not self.is_tag_deprecated(u) and not self.is_tag_deprecated(v)):
                    impl_graph.add_edge(u, v)
        
        # Find all reachable nodes from the starting tag
        if impl_graph.has_node(tag):
            reachable = nx.descendants(impl_graph, tag)
            return reachable
        
        return set()
    
    def get_alias_group(self, tag: str, include_deprecated: bool = False) -> Set[str]:
        """
        Get all tags in the same alias group (connected component of alias edges).
        
        Args:
            tag: The tag to get the alias group for
            include_deprecated: Whether to include deprecated tags
            
        Returns:
            Set of all tags in the same alias group
        """
        if not self.graph.has_node(tag):
            return set()
        
        # Create an undirected subgraph with only alias edges
        alias_graph = nx.Graph()
        for u, v, data in self.graph.edges(data=True):
            if data.get('edge_type') == 'alias':
                if include_deprecated or (not self.is_tag_deprecated(u) and not self.is_tag_deprecated(v)):
                    alias_graph.add_edge(u, v)
        
        # Find connected component containing the tag
        if alias_graph.has_node(tag):
            for component in nx.connected_components(alias_graph):
                if tag in component:
                    return component
        
        return {tag}  # Return singleton set if no aliases
    
    def expand_tags(self, tags: List[str], include_deprecated: bool = False) -> Tuple[Set[str], Dict[str, int]]:
        """
        Expand a list of tags with their implications and aliases.
        
        This is the main high-performance method that replaces the slow individual
        file-based cache lookups.
        
        Args:
            tags: List of input tags to expand
            include_deprecated: Whether to include deprecated tags
            
        Returns:
            Tuple of (expanded_tag_set, frequency_dict)
        """
        # Filter out deprecated input tags
        if not include_deprecated:
            tags = [tag for tag in tags if not self.is_tag_deprecated(tag)]
        
        if not tags:
            return set(), {}
        
        # Start with original tags
        expanded_tags = set(tags)
        frequencies = defaultdict(int)
        
        # Initialize frequencies for original tags
        for tag in tags:
            frequencies[tag] = 1
        
        # Process implications transitively
        processed_implications = set()
        implication_queue = list(tags)
        
        while implication_queue:
            current_tag = implication_queue.pop(0)
            if current_tag in processed_implications:
                continue
            processed_implications.add(current_tag)
            
            # Get direct implications
            implications = self.get_implications(current_tag, include_deprecated)
            for implied_tag in implications:
                if implied_tag not in expanded_tags:
                    expanded_tags.add(implied_tag)
                    implication_queue.append(implied_tag)
                
                # Add frequency from the implying tag
                frequencies[implied_tag] += frequencies[current_tag]
        
        # Process aliases (they share frequency within each group)
        alias_groups = {}
        for tag in list(expanded_tags):
            if tag not in alias_groups:
                group = self.get_alias_group(tag, include_deprecated)
                total_freq = sum(frequencies[t] for t in group if t in frequencies)
                
                # Add all aliases to expanded set
                expanded_tags.update(group)
                
                # Set equal frequency for all aliases in the group
                for alias_tag in group:
                    frequencies[alias_tag] = total_freq
                    alias_groups[alias_tag] = group
        
        return expanded_tags, dict(frequencies)
    
    def load_graph(self, cache_file: str) -> None:
        """
        Load graph from a pickle file.
        
        Args:
            cache_file: Path to the cache file
        """
        try:
            with open(cache_file, 'rb') as f:
                self.graph = pickle.load(f)
            logger.info(f"Loaded tag graph with {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges")
            self._dirty = False
        except Exception as e:
            logger.error(f"Failed to load graph cache: {e}")
            self.graph = nx.MultiDiGraph()
    
    def save_graph(self, cache_file: Optional[str] = None) -> None:
        """
        Save graph to a pickle file.
        
        Args:
            cache_file: Path to save the cache file (uses self.cache_file if None)
        """
        cache_file = cache_file or self.cache_file
        if not cache_file:
            raise ValueError("No cache file specified")
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            
            with open(cache_file, 'wb') as f:
                pickle.dump(self.graph, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.info(f"Saved tag graph with {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges")
            self._dirty = False
        except Exception as e:
            logger.error(f"Failed to save graph cache: {e}")
    
    def auto_save(self) -> None:
        """Save graph if it has been modified."""
        if self._dirty and self.cache_file:
            self.save_graph()
    
    def import_from_json_cache(self, cache_dir: str) -> None:
        """
        Import data from the old JSON file-based cache format.
        
        This method helps migrate from the old individual file cache to the new
        graph-based cache.
        
        Args:
            cache_dir: Directory containing the old JSON cache files
        """
        if not os.path.exists(cache_dir):
            logger.warning(f"Cache directory not found: {cache_dir}")
            return
        
        imported_tags = set()
        
        # Import implications
        for filename in os.listdir(cache_dir):
            if filename.startswith('implications_') and filename.endswith('.json'):
                tag = filename[len('implications_'):-len('.json')]
                tag = self._decode_cache_filename(tag)
                
                try:
                    with open(os.path.join(cache_dir, filename), 'r') as f:
                        implications = json.load(f)
                    
                    # Add tag if not exists
                    if not self.graph.has_node(tag):
                        self.add_tag(tag)
                    
                    # Add implications
                    for implied_tag in implications:
                        self.add_implication(tag, implied_tag)
                    
                    imported_tags.add(tag)
                except Exception as e:
                    logger.error(f"Failed to import implications for {tag}: {e}")
        
        # Import aliases
        for filename in os.listdir(cache_dir):
            if filename.startswith('aliases_') and filename.endswith('.json'):
                tag = filename[len('aliases_'):-len('.json')]
                tag = self._decode_cache_filename(tag)
                
                try:
                    with open(os.path.join(cache_dir, filename), 'r') as f:
                        aliases = json.load(f)
                    
                    # Add tag if not exists
                    if not self.graph.has_node(tag):
                        self.add_tag(tag)
                    
                    # Add aliases
                    for alias_tag in aliases:
                        self.add_alias(tag, alias_tag)
                    
                    imported_tags.add(tag)
                except Exception as e:
                    logger.error(f"Failed to import aliases for {tag}: {e}")
        
        # Import deprecated status
        for filename in os.listdir(cache_dir):
            if filename.startswith('deprecated_') and filename.endswith('.json'):
                tag = filename[len('deprecated_'):-len('.json')]
                tag = self._decode_cache_filename(tag)
                
                try:
                    with open(os.path.join(cache_dir, filename), 'r') as f:
                        is_deprecated = json.load(f)
                    
                    # Update tag with deprecated status
                    if self.graph.has_node(tag):
                        self.graph.nodes[tag]['deprecated'] = is_deprecated
                    else:
                        self.add_tag(tag, is_deprecated=is_deprecated)
                    
                    imported_tags.add(tag)
                except Exception as e:
                    logger.error(f"Failed to import deprecated status for {tag}: {e}")
        
        logger.info(f"Imported {len(imported_tags)} tags from JSON cache")
        self._dirty = True
    
    def _decode_cache_filename(self, encoded_tag: str) -> str:
        """Decode URL-encoded tag name from cache filename."""
        import urllib.parse
        return urllib.parse.unquote(encoded_tag)
    
    def stats(self) -> Dict[str, int]:
        """
        Get statistics about the graph.
        
        Returns:
            Dictionary with graph statistics
        """
        total_nodes = self.graph.number_of_nodes()
        total_edges = self.graph.number_of_edges()
        
        # Count edge types
        implication_edges = 0
        alias_edges = 0
        deprecated_nodes = 0
        
        for u, v, data in self.graph.edges(data=True):
            if data.get('edge_type') == 'implication':
                implication_edges += 1
            elif data.get('edge_type') == 'alias':
                alias_edges += 1
        
        for node, data in self.graph.nodes(data=True):
            if data.get('deprecated', False):
                deprecated_nodes += 1
        
        return {
            'total_nodes': total_nodes,
            'total_edges': total_edges,
            'implication_edges': implication_edges,
            'alias_edges': alias_edges,
            'deprecated_nodes': deprecated_nodes
        }
    
    def mark_tag_fetched(self, tag: str) -> None:
        """Mark a tag as having its relationships fetched from the API."""
        if self.graph.has_node(tag):
            self.graph.nodes[tag]['fetched'] = True
            self._dirty = True
    
    def is_tag_fetched(self, tag: str) -> bool:
        """Check if a tag's relationships have been fetched from the API."""
        if not self.graph.has_node(tag):
            return False
        return self.graph.nodes[tag].get('fetched', False)
    
    def get_unfetched_tags(self, tags: List[str]) -> List[str]:
        """Get list of tags that need their relationships fetched."""
        unfetched = []
        for tag in tags:
            if not self.graph.has_node(tag) or not self.is_tag_fetched(tag):
                unfetched.append(tag)
        return unfetched 