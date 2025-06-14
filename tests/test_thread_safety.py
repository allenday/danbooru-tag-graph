"""Tests for thread safety of DanbooruTagGraph."""

import unittest
import threading
import time
import tempfile
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from danbooru_tag_graph import DanbooruTagGraph


class TestThreadSafety(unittest.TestCase):
    """Test thread safety of DanbooruTagGraph operations."""

    def setUp(self):
        """Set up test case."""
        self.graph = DanbooruTagGraph()
        
    def test_concurrent_tag_addition(self):
        """Test adding tags concurrently from multiple threads."""
        num_threads = 10
        tags_per_thread = 100
        
        def add_tags(thread_id):
            """Add tags in a thread."""
            for i in range(tags_per_thread):
                tag = f"thread_{thread_id}_tag_{i}"
                self.graph.add_tag(tag, is_deprecated=(i % 5 == 0))
        
        threads = []
        for thread_id in range(num_threads):
            thread = threading.Thread(target=add_tags, args=(thread_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all tags were added
        stats = self.graph.stats()
        expected_total = num_threads * tags_per_thread
        self.assertEqual(stats['total_nodes'], expected_total)
        
        # Verify some tags are marked as deprecated
        self.assertGreater(stats['deprecated_nodes'], 0)

    def test_concurrent_implications(self):
        """Test adding implications concurrently."""
        num_threads = 5
        implications_per_thread = 50
        
        def add_implications(thread_id):
            """Add implications in a thread."""
            for i in range(implications_per_thread):
                antecedent = f"t{thread_id}_ante_{i}"
                consequent = f"t{thread_id}_cons_{i}"
                self.graph.add_implication(antecedent, consequent)
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(add_implications, thread_id) 
                for thread_id in range(num_threads)
            ]
            
            # Wait for completion
            for future in as_completed(futures):
                future.result()  # Will raise if there was an exception
        
        stats = self.graph.stats()
        expected_implications = num_threads * implications_per_thread
        self.assertEqual(stats['implication_edges'], expected_implications)

    def test_concurrent_aliases(self):
        """Test adding aliases concurrently."""
        num_threads = 5
        aliases_per_thread = 50
        
        def add_aliases(thread_id):
            """Add aliases in a thread."""
            for i in range(aliases_per_thread):
                tag1 = f"t{thread_id}_alias1_{i}"
                tag2 = f"t{thread_id}_alias2_{i}"
                self.graph.add_alias(tag1, tag2)
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(add_aliases, thread_id) 
                for thread_id in range(num_threads)
            ]
            
            for future in as_completed(futures):
                future.result()
        
        stats = self.graph.stats()
        # Each alias creates 2 bidirectional edges
        expected_alias_edges = num_threads * aliases_per_thread * 2
        self.assertEqual(stats['alias_edges'], expected_alias_edges)

    def test_concurrent_expansion(self):
        """Test tag expansion while modifications happen concurrently."""
        # Set up some initial data
        self.graph.add_tag("cat", fetched=True)
        self.graph.add_tag("animal", fetched=True)
        self.graph.add_tag("feline", fetched=True)
        self.graph.add_implication("cat", "animal")
        self.graph.add_alias("cat", "feline")
        
        expansion_results = []
        modification_complete = threading.Event()
        
        def expand_tags():
            """Continuously expand tags."""
            while not modification_complete.is_set():
                try:
                    expanded, frequencies = self.graph.expand_tags(["cat"])
                    expansion_results.append((expanded, frequencies))
                except Exception as e:
                    self.fail(f"Tag expansion failed: {e}")
                time.sleep(0.001)  # Small delay to allow other threads
        
        def modify_graph():
            """Add more relationships."""
            for i in range(100):
                self.graph.add_tag(f"new_tag_{i}")
                self.graph.add_implication("cat", f"new_tag_{i}")
                time.sleep(0.001)
            modification_complete.set()
        
        # Start threads
        expand_thread = threading.Thread(target=expand_tags)
        modify_thread = threading.Thread(target=modify_graph)
        
        expand_thread.start()
        modify_thread.start()
        
        # Wait for completion
        modify_thread.join()
        expand_thread.join()
        
        # Verify we got some results and no crashes
        self.assertGreater(len(expansion_results), 0)
        
        # Final expansion should include all new implications
        final_expanded, final_frequencies = self.graph.expand_tags(["cat"])
        self.assertGreaterEqual(len(final_expanded), 103)  # cat + animal + feline + 100 new

    def test_concurrent_stats(self):
        """Test getting stats while graph is being modified."""
        stats_results = []
        modification_complete = threading.Event()
        
        def get_stats():
            """Continuously get stats."""
            while not modification_complete.is_set():
                try:
                    stats = self.graph.stats()
                    stats_results.append(stats)
                except Exception as e:
                    self.fail(f"Stats collection failed: {e}")
                time.sleep(0.001)
        
        def modify_graph():
            """Add tags and relationships."""
            for i in range(200):
                self.graph.add_tag(f"stat_tag_{i}")
                if i > 0:
                    self.graph.add_implication(f"stat_tag_{i-1}", f"stat_tag_{i}")
                time.sleep(0.001)
            modification_complete.set()
        
        # Start threads
        stats_thread = threading.Thread(target=get_stats)
        modify_thread = threading.Thread(target=modify_graph)
        
        stats_thread.start()
        modify_thread.start()
        
        # Wait for completion
        modify_thread.join()
        stats_thread.join()
        
        # Verify we collected stats without crashes
        self.assertGreater(len(stats_results), 0)
        
        # Node counts should be monotonically increasing
        for i in range(1, len(stats_results)):
            self.assertGreaterEqual(
                stats_results[i]['total_nodes'], 
                stats_results[i-1]['total_nodes']
            )

    def test_concurrent_save_load(self):
        """Test saving and loading while other operations happen."""
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Set up initial data
            for i in range(50):
                self.graph.add_tag(f"save_tag_{i}")
                if i > 0:
                    self.graph.add_implication(f"save_tag_{i-1}", f"save_tag_{i}")
            
            save_complete = threading.Event()
            
            def modify_graph():
                """Continue modifying while save happens."""
                for i in range(50, 100):
                    self.graph.add_tag(f"save_tag_{i}")
                    if i > 50:
                        self.graph.add_implication(f"save_tag_{i-1}", f"save_tag_{i}")
                    time.sleep(0.001)
                save_complete.set()
            
            def save_graph():
                """Save the graph."""
                time.sleep(0.01)  # Let some modifications happen first
                self.graph.save_graph(tmp_path)
            
            # Start threads
            modify_thread = threading.Thread(target=modify_graph)
            save_thread = threading.Thread(target=save_graph)
            
            modify_thread.start()
            save_thread.start()
            
            # Wait for completion
            modify_thread.join()
            save_thread.join()
            
            # Verify file was created and can be loaded
            self.assertTrue(os.path.exists(tmp_path))
            
            # Load into new graph and verify data
            new_graph = DanbooruTagGraph(tmp_path)
            stats = new_graph.stats()
            
            # Should have at least the initial 50 tags, maybe more
            self.assertGreaterEqual(stats['total_nodes'], 50)
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_no_deadlocks(self):
        """Test that complex operations don't cause deadlocks."""
        operations_complete = threading.Event()
        
        def mixed_operations(thread_id):
            """Perform mixed read/write operations."""
            for i in range(50):
                tag = f"mixed_{thread_id}_{i}"
                
                # Add tag
                self.graph.add_tag(tag)
                
                # Add some relationships
                if i > 0:
                    prev_tag = f"mixed_{thread_id}_{i-1}"
                    self.graph.add_implication(prev_tag, tag)
                
                # Read operations
                self.graph.is_tag_deprecated(tag)
                self.graph.get_implications(tag)
                self.graph.get_aliases(tag)
                
                # Stats
                if i % 10 == 0:
                    self.graph.stats()
                
                time.sleep(0.0001)  # Very small delay
        
        # Run multiple threads with mixed operations
        num_threads = 8
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(mixed_operations, thread_id) 
                for thread_id in range(num_threads)
            ]
            
            # Wait with timeout to detect deadlocks
            for future in as_completed(futures, timeout=30):
                future.result()  # Will raise if there was an exception
        
        # If we get here, no deadlocks occurred
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main() 