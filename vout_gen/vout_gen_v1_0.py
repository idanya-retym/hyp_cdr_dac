#!/usr/bin/env python3
"""
Generate 256 vout signal names in the pattern:
vout3<63>,vout2<63>,vout1<63>,vout0<63>,vout3<62>,...,vout0<0>
"""

def main():
    try:
        signals = []
        for idx in range(63, -1, -1):
            for vout in range(3, -1, -1):
                signals.append(f"vout{vout}<{idx}>")

        output = ",".join(signals)
        print(output)
        print(f"\nTotal count: {len(signals)}")

    except Exception as e:
        print(f"Error: {e}")
        raise

if __name__ == "__main__":
    main()
