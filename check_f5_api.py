#!/usr/bin/env python3
"""
Quick script to check F5-TTS API parameters
"""

try:
    from f5_tts.api import F5TTS
    import inspect

    # Initialize F5TTS
    model = F5TTS()

    # Get infer method signature
    sig = inspect.signature(model.infer)

    print("=" * 60)
    print("F5TTS.infer() method signature:")
    print("=" * 60)
    print(f"\n{sig}\n")

    print("=" * 60)
    print("Parameters:")
    print("=" * 60)
    for param_name, param in sig.parameters.items():
        print(f"  - {param_name}: {param.annotation if param.annotation != inspect.Parameter.empty else 'no type'}")
        if param.default != inspect.Parameter.empty:
            print(f"    (default: {param.default})")

    print("\n" + "=" * 60)
    print("✅ F5-TTS API check complete!")
    print("=" * 60)

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
