#!/bin/bash
# Testar båda Vapi-formaten mot place_order och vapi/webhook

BASE="http://localhost:8000"
ORDER='{"items":[{"id":13,"name":"Kebabpizza","quantity":1},{"id":401,"name":"Coca-Cola","quantity":1}],"special_requests":"test"}'

echo "=== 1. Direkt format (place_order) ==="
curl -s -X POST "$BASE/place_order" -H "Content-Type: application/json" -d "{\"items\":[{\"id\":13,\"name\":\"Kebabpizza\",\"quantity\":1},{\"id\":401,\"name\":\"Coca-Cola\",\"quantity\":1}],\"special_requests\":\"curl test\"}" | python3 -m json.tool

echo ""
echo "=== 2. Gammalt Vapi-format (toolWithToolCallList) ==="
curl -s -X POST "$BASE/place_order" -H "Content-Type: application/json" -d '{
  "message": {
    "type": "tool-calls",
    "toolWithToolCallList": [{
      "name": "place_order",
      "toolCall": {
        "id": "test-old",
        "parameters": {
          "items": [{"id": 4, "name": "Hawaii", "quantity": 1}],
          "special_requests": "gammalt format"
        }
      }
    }]
  }
}' | python3 -m json.tool

echo ""
echo "=== 3. Nytt Vapi-format (toolCallList) ==="
curl -s -X POST "$BASE/place_order" -H "Content-Type: application/json" -d '{
  "message": {
    "type": "tool-calls",
    "toolCallList": [{
      "id": "test-new",
      "function": {
        "name": "place_order",
        "arguments": {
          "items": [{"id": 13, "name": "Kebabpizza", "quantity": 1}],
          "special_requests": "nytt format"
        }
      }
    }]
  }
}' | python3 -m json.tool

echo ""
echo "=== 4. Webhook med nytt format ==="
curl -s -X POST "$BASE/vapi/webhook" -H "Content-Type: application/json" -d '{
  "message": {
    "type": "tool-calls",
    "toolCallList": [{
      "id": "webhook-test",
      "function": {
        "name": "place_order",
        "arguments": {
          "items": [{"id": 2, "name": "Vesuvio", "quantity": 1}],
          "special_requests": "via webhook"
        }
      }
    }]
  }
}' | python3 -m json.tool

echo ""
echo "Klar! Kolla terminalen för köksbongar."
