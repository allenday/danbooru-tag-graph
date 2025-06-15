"""Tests for DanbooruTagGraph class."""

import unittest
import tempfile
import os
from danbooru_tag_graph import DanbooruTagGraph


class TestDanbooruTagGraph(unittest.TestCase):
    """Test cases for DanbooruTagGraph."""

    def setUp(self):
        """Set up test case."""
        self.graph = DanbooruTagGraph()

    def test_add_tag(self):
        """Test adding tags to the graph."""
        self.graph.add_tag("cat", is_deprecated=False, fetched=True)
        
        self.assertTrue(self.graph.graph.has_node("cat"))
        self.assertFalse(self.graph.is_tag_deprecated("cat"))
        self.assertTrue(self.graph.is_tag_fetched("cat"))

    def test_add_implication(self):
        """Test adding implications."""
        self.graph.add_implication("cat", "animal")
        
        implications = self.graph.get_implications("cat")
        self.assertIn("animal", implications)

    def test_add_alias(self):
        """Test adding aliases."""
        self.graph.add_alias("cat", "feline")
        
        # Test directional behavior: cat -> feline
        aliases = self.graph.get_aliases("cat")
        self.assertIn("feline", aliases)
        
        # feline should not have outgoing aliases
        reverse_aliases = self.graph.get_aliases("feline")
        self.assertEqual(reverse_aliases, [])
        
        # Test reverse lookup
        aliased_from = self.graph.get_aliased_from("feline")
        self.assertIn("cat", aliased_from)

    def test_transitive_implications(self):
        """Test transitive implications."""
        self.graph.add_implication("kitten", "cat")
        self.graph.add_implication("cat", "animal")
        
        transitive = self.graph.get_transitive_implications("kitten")
        self.assertIn("cat", transitive)
        self.assertIn("animal", transitive)

    def test_expand_tags(self):
        """Test tag expansion with frequencies."""
        # Set up test data
        self.graph.add_tag("cat", fetched=True)
        self.graph.add_tag("animal", fetched=True)
        self.graph.add_tag("feline", fetched=True)
        
        self.graph.add_implication("cat", "animal")
        self.graph.add_alias("old_cat", "cat")  # old_cat -> cat (directional)
        
        # Test expansion with canonical tag
        expanded_tags, frequencies = self.graph.expand_tags(["cat"])
        
        expected_tags = {"cat", "animal"}  # cat and its implication
        self.assertLessEqual(expected_tags, expanded_tags)  # Should contain at least these
        
        # Check frequencies
        self.assertEqual(frequencies["cat"], 1)
        self.assertEqual(frequencies["animal"], 1)  # From cat implication
        
        # Test expansion with antecedent tag (should resolve to canonical)
        expanded_tags_2, frequencies_2 = self.graph.expand_tags(["old_cat"])
        
        # Should include both old_cat and canonical form cat + implications
        self.assertIn("cat", expanded_tags_2)  # Canonical form
        self.assertIn("animal", expanded_tags_2)  # Implication from canonical
        self.assertIn("old_cat", expanded_tags_2)  # Original antecedent
        
        # Frequency should be on canonical form
        self.assertEqual(frequencies_2["cat"], 1)

    def test_save_load_graph(self):
        """Test saving and loading graph."""
        # Set up test data
        self.graph.add_tag("cat", fetched=True)
        self.graph.add_implication("cat", "animal")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            self.graph.save_graph(tmp_path)
            
            # Load into new graph
            new_graph = DanbooruTagGraph(tmp_path)
            
            # Verify data was preserved
            self.assertTrue(new_graph.graph.has_node("cat"))
            self.assertTrue(new_graph.is_tag_fetched("cat"))
            implications = new_graph.get_implications("cat")
            self.assertIn("animal", implications)
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_get_unfetched_tags(self):
        """Test getting unfetched tags."""
        self.graph.add_tag("cat", fetched=True)
        self.graph.add_tag("dog", fetched=False)
        
        unfetched = self.graph.get_unfetched_tags(["cat", "dog", "bird"])
        
        # Should include dog (fetched=False) and bird (doesn't exist)
        self.assertIn("dog", unfetched)
        self.assertIn("bird", unfetched)
        self.assertNotIn("cat", unfetched)

    def test_stats(self):
        """Test graph statistics."""
        self.graph.add_tag("cat", is_deprecated=False)
        self.graph.add_tag("old_tag", is_deprecated=True)
        self.graph.add_implication("cat", "animal")
        self.graph.add_alias("cat", "feline")
        
        stats = self.graph.stats()
        
        self.assertEqual(stats['total_nodes'], 4)  # cat, old_tag, animal, feline
        self.assertEqual(stats['deprecated_nodes'], 1)  # old_tag
        self.assertGreater(stats['implication_edges'], 0)
        self.assertGreater(stats['alias_edges'], 0)


if __name__ == '__main__':
    unittest.main() 