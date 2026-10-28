def retrieve(store, gateway, question, candidate_ids):
    vector = gateway.embed([question])[0]
    if candidate_ids:
        # The same budget per candidate prevents a comparison starving one side.
        return [
            chunk for candidate_id in candidate_ids
            for chunk in store.search(vector, candidate_id, k=4)
        ]
    return store.search(vector, k=8)