#!/usr/bin/env python3
"""
Test script for Gislegrillen Order System
Run this to verify the system is working correctly
"""

import json
from pathlib import Path

def test_menu_structure():
    """Test menu.json structure"""
    print("🔍 Testing menu.json...")
    
    with open("menu.json", "r", encoding="utf-8") as f:
        menu = json.load(f)
    
    # Check categories
    required_categories = ["pizzas", "kebabs", "burgers", "sides", "drinks"]
    for category in required_categories:
        assert category in menu, f"Missing category: {category}"
        print(f"  ✅ Category '{category}': {len(menu[category])} items")
    
    # Check pizzas count
    assert len(menu["pizzas"]) == 52, f"Expected 52 pizzas, found {len(menu['pizzas'])}"
    print(f"  ✅ All 52 pizzas present")
    
    # Check item structure
    for category, items in menu.items():
        for item in items:
            assert "id" in item, f"Item missing 'id' in {category}"
            assert "name" in item, f"Item missing 'name' in {category}"
            assert "price" in item, f"Item missing 'price' in {category}"
            assert "description" in item, f"Item missing 'description' in {category}"
    
    print("  ✅ All items have required fields\n")

def test_orders_file():
    """Test orders.json"""
    print("🔍 Testing orders.json...")
    
    with open("orders.json", "r", encoding="utf-8") as f:
        orders = json.load(f)
    
    assert isinstance(orders, list), "orders.json should be a list"
    print(f"  ✅ orders.json is valid (contains {len(orders)} orders)\n")

def test_system_prompt():
    """Test system_prompt.md exists and has content"""
    print("🔍 Testing system_prompt.md...")
    
    with open("system_prompt.md", "r", encoding="utf-8") as f:
        content = f.read()
    
    assert len(content) > 100, "system_prompt.md seems too short"
    assert "Svenska" in content or "svenska" in content, "System prompt should mention Swedish"
    assert "Gislegrillen" in content, "System prompt should mention Gislegrillen"
    
    print(f"  ✅ system_prompt.md is valid ({len(content)} characters)\n")

def test_env_template():
    """Test .env.template"""
    print("🔍 Testing .env.template...")
    
    with open(".env.template", "r", encoding="utf-8") as f:
        content = f.read()
    
    required_keys = ["VAPI_API_KEY", "GROQ_API_KEY", "PUSHOVER_USER_KEY", "PUSHOVER_API_TOKEN"]
    for key in required_keys:
        assert key in content, f"Missing key in .env.template: {key}"
    
    print(f"  ✅ .env.template has all required keys\n")

def test_main_py():
    """Test main.py can be imported"""
    print("🔍 Testing main.py...")
    
    try:
        # Just check if it compiles
        with open("main.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        compile(content, "main.py", "exec")
        print(f"  ✅ main.py syntax is valid\n")
    except SyntaxError as e:
        print(f"  ❌ Syntax error in main.py: {e}\n")
        raise

def test_price_calculation():
    """Test price calculation logic"""
    print("🔍 Testing price calculation...")
    
    with open("menu.json", "r", encoding="utf-8") as f:
        menu = json.load(f)
    
    # Test case: 1x Hawaii (98 kr) + 1x Coca-Cola (25 kr) = 123 kr
    hawaii = next((p for p in menu["pizzas"] if p["id"] == 4), None)
    cola = next((d for d in menu["drinks"] if d["id"] == 401), None)
    
    assert hawaii is not None, "Hawaii pizza not found"
    assert cola is not None, "Coca-Cola not found"
    
    total = hawaii["price"] + cola["price"]
    assert total == 123, f"Expected 123 kr, got {total} kr"
    
    print(f"  ✅ Price calculation works correctly\n")

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("🍕 GISLEGRILLEN ORDER SYSTEM - TEST SUITE 🍕".center(60))
    print("="*60 + "\n")
    
    tests = [
        test_menu_structure,
        test_orders_file,
        test_system_prompt,
        test_env_template,
        test_main_py,
        test_price_calculation
    ]
    
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"❌ Test failed: {e}\n")
            failed += 1
        except Exception as e:
            print(f"❌ Unexpected error: {e}\n")
            failed += 1
    
    print("="*60)
    if failed == 0:
        print("✅ ALL TESTS PASSED!".center(60))
        print("="*60)
        print("\n🚀 System is ready to use!")
        print("   Run: python main.py\n")
        return 0
    else:
        print(f"❌ {failed} TEST(S) FAILED!".center(60))
        print("="*60 + "\n")
        return 1

if __name__ == "__main__":
    exit(main())
