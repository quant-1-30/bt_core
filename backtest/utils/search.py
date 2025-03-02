#! /usr/bin/env python
# -*- coding: utf-8 -*-

from collections import deque, defaultdict


# def bfs_search(graph, starts, level):
#         if not level:
#             return list(starts) 
#         visited = set()  # To track visited nodes
#         queue = deque([(start, 0) for start in starts])  # Initialize queue with nodes and their level (0)
#         for start in starts:
#             visited.add(start)  # Mark all start nodes as visited

#         nodes_at_level = []  # List to hold nodes at the desired level

#         while queue:
#             node, current_level = queue.popleft()  # Dequeue node and its level

#             # If we've reached the desired level, add node to result list
#             if current_level == level:
#                 nodes_at_level.append(node)

#             # If we're below the desired level, enqueue neighbors with level + 1
#             if current_level < level:
#                 for neighbor in graph[node]:
#                     if neighbor not in visited:
#                         visited.add(neighbor)
#                         queue.append((neighbor, current_level + 1))
    
#         return nodes_at_level


def bfs_by_level(G, start_nodes):
    visited = set()  # To track visited nodes
    queue = deque([(start, 0) for start in start_nodes])  # Initialize queue with nodes and their level (0)
    for start in start_nodes:
        visited.add(start)  # Mark all start nodes as v
    
    levels = defaultdict(list)

    while queue:
        node, current_level = queue.popleft()

        # Add the node to the corresponding level in the levels dictionary
        if current_level not in levels:
            levels[current_level].append(node)

        # Enqueue all unvisited neighbors with the incremented level
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, current_level + 1))

    return levels

