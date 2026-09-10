#!/usr/bin/env python3
"""무해한 텍스트 변환. 부작용·네트워크 호출 없음."""
import sys

def transform(label):
    return f'{label.upper()} :: probe_skill_norm_2-OK'

if __name__ == '__main__':
    print(transform(sys.argv[1] if len(sys.argv) > 1 else 'demo'))
