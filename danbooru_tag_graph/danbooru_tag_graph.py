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
import threading
from typing import Dict, List, Set, Optional, Tuple, Union
from collections import defaultdict
import networkx as nx

logger = logging.getLogger(__name__)


class DanbooruTagGraph:
    """
    A NetworkX-based graph for efficiently managing Danbooru tag relationships.
    
    This class provides high-performance caching and querying of tag implications,
    aliases, and deprecated status using a directed graph structure.
    
    Thread Safety:
    - All public methods are thread-safe and can be called concurrently
    - Internal locking protects graph mutations and iterations
    - Safe for multi-threaded tag expansion and relationship building
    
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
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        
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
        with self._lock:
            self.graph.add_node(tag, deprecated=is_deprecated, fetched=fetched, **metadata)
            self._dirty = True
    
    def add_implication(self, antecedent: str, consequent: str) -> None:
        """
        Add an implication relationship: antecedent -> consequent.
        
        Args:
            antecedent: The tag that implies another
            consequent: The tag that is implied
        """
        with self._lock:
            # Ensure both nodes exist
            if not self.graph.has_node(antecedent):
                self.graph.add_node(antecedent)
            if not self.graph.has_node(consequent):
                self.graph.add_node(consequent)
            
            # Add implication edge
            self.graph.add_edge(antecedent, consequent, edge_type='implication')
            self._dirty = True
    
    def add_alias(self, antecedent: str, consequent: str) -> None:
        """
        Add a directional alias relationship: antecedent -> consequent.
        
        In Danbooru's system:
        - antecedent: The deprecated/old tag that redirects to another
        - consequent: The canonical/preferred tag that should be used
        
        Args:
            antecedent: The tag that is aliased (deprecated/old)
            consequent: The tag that is the alias target (canonical/preferred)
        """
        with self._lock:
            # Ensure both nodes exist
            if not self.graph.has_node(antecedent):
                self.graph.add_node(antecedent)
            if not self.graph.has_node(consequent):
                self.graph.add_node(consequent)
            
            # Add single directional alias edge: antecedent -> consequent
            self.graph.add_edge(antecedent, consequent, edge_type='alias')
            self._dirty = True
    
    def is_tag_deprecated(self, tag: str) -> bool:
        """
        Check if a tag is deprecated.
        
        Args:
            tag: The tag to check
            
        Returns:
            True if deprecated, False otherwise
        """
        with self._lock:
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
        with self._lock:
            if not self.graph.has_node(tag):
                return []
            
            implications = []
            for successor in self.graph.successors(tag):
                # Check if edge is an implication
                edge_data = self.graph.get_edge_data(tag, successor)
                for edge in edge_data.values():
                    if edge.get('edge_type') == 'implication':
                        if include_deprecated or not self.graph.nodes[successor].get('deprecated', False):
                            implications.append(successor)
                        break
            
            return implications
    
    def get_aliases(self, tag: str, include_deprecated: bool = False) -> List[str]:
        """
        Get all tags that this tag is aliased TO (outgoing aliases: antecedent -> consequent).
        
        This returns the canonical/preferred tags that this tag redirects to.
        
        Args:
            tag: The tag to get aliases for
            include_deprecated: Whether to include deprecated consequent tags
            
        Returns:
            List of consequent tag names (canonical targets)
        """
        with self._lock:
            if not self.graph.has_node(tag):
                return []
            
            aliases = []
            # Only check successors (outgoing edges) for alias relationships
            for successor in self.graph.successors(tag):
                # Check if edge is an alias (antecedent -> consequent)
                edge_data = self.graph.get_edge_data(tag, successor)
                for edge in edge_data.values():
                    if edge.get('edge_type') == 'alias':
                        if include_deprecated or not self.graph.nodes[successor].get('deprecated', False):
                            aliases.append(successor)
                        break
            
            return aliases
    
    def get_aliased_from(self, tag: str, include_deprecated: bool = True) -> List[str]:
        """
        Get all tags that are aliased TO this tag (incoming aliases: antecedent -> consequent).
        
        This returns the deprecated/old tags that redirect to this canonical tag.
        Note: Default includes deprecated tags since antecedents are typically deprecated.
        
        Args:
            tag: The tag to get incoming aliases for
            include_deprecated: Whether to include deprecated antecedent tags (default: True)
            
        Returns:
            List of antecedent tag names (deprecated sources)
        """
        with self._lock:
            if not self.graph.has_node(tag):
                return []
            
            aliased_from = []
            # Only check predecessors (incoming edges) for alias relationships
            for predecessor in self.graph.predecessors(tag):
                # Check if edge is an alias (predecessor -> tag)
                edge_data = self.graph.get_edge_data(predecessor, tag)
                for edge in edge_data.values():
                    if edge.get('edge_type') == 'alias':
                        # Include if we want deprecated tags OR if the predecessor is not deprecated
                        if include_deprecated or not self.graph.nodes[predecessor].get('deprecated', False):
                            aliased_from.append(predecessor)
                        break
            
            return aliased_from
    
    def is_canonical(self, tag: str) -> bool:
        """
        Check if a tag is canonical (not an antecedent in any alias relationship).
        
        A canonical tag is one that doesn't have outgoing alias edges, meaning
        it's not deprecated/redirected to another tag.
        
        Args:
            tag: The tag to check
            
        Returns:
            True if the tag is canonical (no outgoing aliases), False otherwise
        """
        with self._lock:
            if not self.graph.has_node(tag):
                return True  # Non-existent tags are considered canonical
            
            # Check if tag has any outgoing alias edges
            for successor in self.graph.successors(tag):
                edge_data = self.graph.get_edge_data(tag, successor)
                for edge in edge_data.values():
                    if edge.get('edge_type') == 'alias':
                        return False  # Has outgoing alias, so not canonical
            
            return True  # No outgoing aliases, so canonical
    
    def get_transitive_implications(self, tag: str, include_deprecated: bool = False) -> Set[str]:
        """
        Get all tags implied by this tag transitively (following the implication chain).
        
        Args:
            tag: The starting tag
            include_deprecated: Whether to include deprecated tags
            
        Returns:
            Set of all transitively implied tag names
        """
        with self._lock:
            if not self.graph.has_node(tag):
                return set()
            
            # Create a subgraph with only implication edges
            impl_graph = nx.DiGraph()
            for u, v, data in self.graph.edges(data=True):
                if data.get('edge_type') == 'implication':
                    u_deprecated = self.graph.nodes[u].get('deprecated', False)
                    v_deprecated = self.graph.nodes[v].get('deprecated', False)
                    if include_deprecated or (not u_deprecated and not v_deprecated):
                        impl_graph.add_edge(u, v)
            
            # Find all reachable nodes from the starting tag
            if impl_graph.has_node(tag):
                reachable = nx.descendants(impl_graph, tag)
                return reachable
            
            return set()
    
    def get_alias_group(self, tag: str, include_deprecated: bool = False) -> Set[str]:
        """
        Get all tags in the same alias group (connected component of alias edges).
        
        This follows the alias chain to find all related tags, both antecedents and consequents.
        
        Args:
            tag: The tag to get the alias group for
            include_deprecated: Whether to include deprecated tags
            
        Returns:
            Set of all tags in the same alias group
        """
        with self._lock:
            if not self.graph.has_node(tag):
                return set()
            
            # Create an undirected subgraph with only alias edges to find connected components
            alias_graph = nx.Graph()
            for u, v, data in self.graph.edges(data=True):
                if data.get('edge_type') == 'alias':
                    u_deprecated = self.graph.nodes[u].get('deprecated', False)
                    v_deprecated = self.graph.nodes[v].get('deprecated', False)
                    if include_deprecated or (not u_deprecated and not v_deprecated):
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
        
        This method now correctly handles directional aliases:
        - Resolves antecedent tags to their canonical consequents
        - Includes all tags in alias groups for frequency calculation
        - Processes implications from canonical forms
        
        Args:
            tags: List of input tags to expand
            include_deprecated: Whether to include deprecated tags
            
        Returns:
            Tuple of (expanded_tag_set, frequency_dict)
        """
        with self._lock:
            # Filter out deprecated input tags
            if not include_deprecated:
                tags = [tag for tag in tags if not self.graph.has_node(tag) or not self.graph.nodes[tag].get('deprecated', False)]
            
            if not tags:
                return set(), {}
            
            # Step 1: Resolve input tags to their canonical forms via aliases
            canonical_tags = set()
            tag_to_canonical = {}  # Track mapping for frequency calculation
            
            for tag in tags:
                # Follow alias chain to find canonical form
                canonical = self._resolve_to_canonical(tag)
                canonical_tags.add(canonical)
                tag_to_canonical[tag] = canonical
            
            # Start with canonical tags
            expanded_tags = set(canonical_tags)
            frequencies = defaultdict(int)
            
            # Initialize frequencies for canonical tags
            for original_tag in tags:
                canonical = tag_to_canonical[original_tag]
                frequencies[canonical] += 1
            
            # Step 2: Process implications transitively from canonical tags
            processed_implications = set()
            implication_queue = list(canonical_tags)
            
            while implication_queue:
                current_tag = implication_queue.pop(0)
                if current_tag in processed_implications:
                    continue
                processed_implications.add(current_tag)
                
                # Get direct implications (thread-safe since we hold the lock)
                implications = self._get_implications_unlocked(current_tag, include_deprecated)
                for implied_tag in implications:
                    if implied_tag not in expanded_tags:
                        expanded_tags.add(implied_tag)
                        implication_queue.append(implied_tag)
                    
                    # Add frequency from the implying tag
                    frequencies[implied_tag] += frequencies[current_tag]
            
            # Step 3: Include all tags in alias groups for comprehensive expansion
            all_related_tags = set(expanded_tags)
            for tag in list(expanded_tags):
                alias_group = self._get_alias_group_unlocked(tag, include_deprecated)
                all_related_tags.update(alias_group)
                
                # Distribute frequency to all members of alias group
                base_freq = frequencies.get(tag, 0)
                for alias_tag in alias_group:
                    if alias_tag not in frequencies:
                        frequencies[alias_tag] = base_freq
            
            return all_related_tags, dict(frequencies)

    def _resolve_to_canonical(self, tag: str) -> str:
        """
        Resolve a tag to its canonical form by following alias chain.
        
        This follows outgoing alias edges (antecedent -> consequent) until
        reaching a tag with no outgoing aliases (canonical form).
        
        Args:
            tag: The tag to resolve
            
        Returns:
            The canonical tag name
        """
        visited = set()
        current = tag
        
        while current not in visited:
            visited.add(current)
            aliases = self._get_aliases_unlocked(current)
            
            if not aliases:
                # No outgoing aliases, this is canonical
                return current
            
            # Follow the first alias (should typically be only one)
            current = aliases[0]
        
        # If we hit a cycle, return the original tag
        return tag

    def _get_aliases_unlocked(self, tag: str, include_deprecated: bool = False) -> List[str]:
        """Internal method to get outgoing aliases without acquiring lock."""
        if not self.graph.has_node(tag):
            return []
        
        aliases = []
        for successor in self.graph.successors(tag):
            edge_data = self.graph.get_edge_data(tag, successor)
            for edge in edge_data.values():
                if edge.get('edge_type') == 'alias':
                    if include_deprecated or not self.graph.nodes[successor].get('deprecated', False):
                        aliases.append(successor)
                    break
        
        return aliases

    def _get_implications_unlocked(self, tag: str, include_deprecated: bool = False) -> List[str]:
        """Internal method to get implications without acquiring lock."""
        if not self.graph.has_node(tag):
            return []
        
        implications = []
        for successor in self.graph.successors(tag):
            # Check if edge is an implication
            edge_data = self.graph.get_edge_data(tag, successor)
            for edge in edge_data.values():
                if edge.get('edge_type') == 'implication':
                    if include_deprecated or not self.graph.nodes[successor].get('deprecated', False):
                        implications.append(successor)
                    break
        
        return implications

    def _get_alias_group_unlocked(self, tag: str, include_deprecated: bool = False) -> Set[str]:
        """Internal method to get alias group without acquiring lock."""
        if not self.graph.has_node(tag):
            return set()
        
        # Create an undirected subgraph with only alias edges
        alias_graph = nx.Graph()
        for u, v, data in self.graph.edges(data=True):
            if data.get('edge_type') == 'alias':
                u_deprecated = self.graph.nodes[u].get('deprecated', False)
                v_deprecated = self.graph.nodes[v].get('deprecated', False)
                if include_deprecated or (not u_deprecated and not v_deprecated):
                    alias_graph.add_edge(u, v)
        
        # Find connected component containing the tag
        if alias_graph.has_node(tag):
            for component in nx.connected_components(alias_graph):
                if tag in component:
                    return component
        
        return {tag}  # Return singleton set if no aliases
    
    def load_graph(self, cache_file: str) -> None:
        """
        Load graph from a pickle file.
        
        Args:
            cache_file: Path to the cache file
        """
        with self._lock:
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
        
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
                            self.graph.add_node(tag)
                        
                        # Add implications
                        for implied_tag in implications:
                            if not self.graph.has_node(implied_tag):
                                self.graph.add_node(implied_tag)
                            self.graph.add_edge(tag, implied_tag, edge_type='implication')
                        
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
                            self.graph.add_node(tag)
                        
                        # Add aliases - the file contains consequents for this antecedent
                        for alias_tag in aliases:
                            if not self.graph.has_node(alias_tag):
                                self.graph.add_node(alias_tag)
                            # Add single directional alias edge: antecedent -> consequent
                            self.graph.add_edge(tag, alias_tag, edge_type='alias')
                        
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
                            self.graph.add_node(tag, deprecated=is_deprecated)
                        
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
        with self._lock:
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
        with self._lock:
            if self.graph.has_node(tag):
                self.graph.nodes[tag]['fetched'] = True
                self._dirty = True
    
    def is_tag_fetched(self, tag: str) -> bool:
        """Check if a tag's relationships have been fetched from the API."""
        with self._lock:
            if not self.graph.has_node(tag):
                return False
            return self.graph.nodes[tag].get('fetched', False)
    
    def get_unfetched_tags(self, tags: List[str]) -> List[str]:
        """Get list of tags that need their relationships fetched."""
        with self._lock:
            unfetched = []
            for tag in tags:
                if not self.graph.has_node(tag) or not self.graph.nodes[tag].get('fetched', False):
                    unfetched.append(tag)
            return unfetched 