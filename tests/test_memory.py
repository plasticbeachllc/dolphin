import requests
from tests.utils import wait_for_endpoint


def run_test(base_url):
    """Tests the Knowledge Graph MCP through a full CRUD lifecycle."""
    base_endpoint = f"{base_url}/memory"
    wait_for_endpoint(base_endpoint)
    headers = {"Accept": "application/json, text/event-stream"}

    # --- Test Data ---
    entity1 = {"name": "Gemini Code Assist", "entityType": "AI", "observations": ["is a coding assistant"]}
    entity2 = {"name": "Python", "entityType": "Programming Language", "observations": ["is dynamically typed"]}

    # 1. CREATE entities
    print("  - Creating entities...")
    create_entities_endpoint = f"{base_endpoint}/create_entities"
    create_payload = {"entities": [entity1, entity2]}
    response = requests.post(create_entities_endpoint, json=create_payload, headers=headers)
    response.raise_for_status()
    assert response.status_code == 200, "Failed to create entities"

    # 2. CREATE a relation
    print("  - Creating a relation...")
    create_relation_endpoint = f"{base_endpoint}/create_relations"
    relation_payload = {"relations": [{"from": "Gemini Code Assist", "to": "Python", "relationType": "USES"}]}
    response = requests.post(create_relation_endpoint, json=relation_payload, headers=headers)
    response.raise_for_status()
    assert response.status_code == 200, "Failed to create relation"

    # 3. READ the graph to verify creation
    print("  - Reading graph to verify...")
    read_graph_endpoint = f"{base_endpoint}/read_graph"
    response = requests.post(read_graph_endpoint, json=None, headers=headers)
    response.raise_for_status()
    graph = response.json()
    assert 'entities' in graph, 'Entities not retrieved'
    assert len(graph['entities']) == 2, 'Incorrect number of entities'
    assert len([obj for obj in graph['entities'] if obj['name'] == 'Gemini Code Assist']) == 1, 'Entity 1 not found'
    assert len([obj for obj in graph['entities'] if obj['name'] == 'Python']) == 1, 'Entity 2 not found'

    # 4. ADD an observation
    print("  - Adding an observation...")
    add_obs_endpoint = f"{base_endpoint}/add_observations"
    obs_payload = {"observations": [{"entityName": "Python", "contents": ["is popular for data science"]}]}
    response = requests.post(add_obs_endpoint, json=obs_payload, headers=headers)
    response.raise_for_status()
    assert response.status_code == 200, "Failed to add observation"

    # 5. SEARCH for a node
    print("  - Searching for a node...")
    search_endpoint = f"{base_endpoint}/search_nodes"
    search_payload = {"query": "data science"}
    response = requests.post(search_endpoint, json=search_payload, headers=headers)
    response.raise_for_status()
    search_results = response.json()
    assert len([obj for obj in search_results["entities"] if obj["name"] == "Python"]) == 1, "Search did not find the entity by observation"

    # 6. DELETE the relation
    print("  - Deleting the relation...")
    delete_relation_endpoint = f"{base_endpoint}/delete_relations"
    del_relation_payload = {"relations": [{"from": "Gemini Code Assist", "to": "Python", "relationType": "USES"}]}
    response = requests.post(delete_relation_endpoint, json=del_relation_payload, headers=headers)
    response.raise_for_status()
    assert response.status_code == 200, "Failed to delete relation"

    # 7. DELETE the entities (should also cascade delete any remaining relations)
    print("  - Deleting entities...")
    delete_entities_endpoint = f"{base_endpoint}/delete_entities"
    delete_payload = {"entityNames": ["Gemini Code Assist", "Python"]}
    response = requests.post(delete_entities_endpoint, json=delete_payload, headers=headers)
    response.raise_for_status()
    assert response.status_code == 200, "Failed to delete entities"

    # 8. READ the graph again to verify deletion
    print("  - Reading graph to verify deletion...")
    response = requests.post(read_graph_endpoint, json={}, headers=headers)
    response.raise_for_status()
    final_graph = response.json()
    assert "Gemini Code Assist" not in final_graph["entities"], "Entity 1 was not deleted"
    assert "Python" not in final_graph["entities"], "Entity 2 was not deleted"
    assert not final_graph["relations"], "Relations were not fully deleted"

    print("Knowledge Graph MCP: All operations successful.")
