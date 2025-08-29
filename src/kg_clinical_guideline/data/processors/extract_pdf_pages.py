#!/usr/bin/env python3
"""
PDF를 페이지별로 JSON으로 추출하는 스크립트
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
import argparse

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False


def extract_pdf_pages_pdfplumber(pdf_path: str) -> Dict[str, str]:
    """pdfplumber를 사용하여 PDF를 페이지별로 추출"""
    pages_data = {}
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        
        for page_num, page in enumerate(pdf.pages, 1):
            # 텍스트 추출
            text = page.extract_text() or ""
            
            # 페이지 키 생성
            page_key = f"page_{page_num}"
            pages_data[page_key] = text.strip()
            
            print(f"페이지 {page_num}/{total_pages} 처리 완료")
    
    return pages_data


def extract_pdf_pages_pypdf2(pdf_path: str) -> Dict[str, str]:
    """PyPDF2를 사용하여 PDF를 페이지별로 추출"""
    pages_data = {}
    
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        total_pages = len(pdf_reader.pages)
        
        for page_num, page in enumerate(pdf_reader.pages, 1):
            # 텍스트 추출
            text = page.extract_text() or ""
            
            # 페이지 키 생성
            page_key = f"page_{page_num}"
            pages_data[page_key] = text.strip()
            
            print(f"페이지 {page_num}/{total_pages} 처리 완료")
    
    return pages_data


def extract_pdf_pages(pdf_path: str, output_file: str = None) -> Dict[str, str]:
    """PDF를 페이지별로 추출"""
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
    
    print(f"PDF 파일 처리 중: {pdf_path.name}")
    
    # 추출 방법 선택
    if HAS_PDFPLUMBER:
        print("pdfplumber를 사용하여 추출합니다...")
        pages_data = extract_pdf_pages_pdfplumber(pdf_path)
    elif HAS_PYPDF2:
        print("PyPDF2를 사용하여 추출합니다...")
        pages_data = extract_pdf_pages_pypdf2(pdf_path)
    else:
        raise ImportError("PDF 처리를 위한 라이브러리가 설치되지 않았습니다. 'pip install pdfplumber' 또는 'pip install PyPDF2'를 실행하세요.")
    
    # 출력 파일명 설정
    if output_file is None:
        output_file = pdf_path.parent / f"{pdf_path.stem}.json"
    
    output_file = Path(output_file)
    
    # JSON 파일 저장
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(pages_data, f, ensure_ascii=False, indent=2)
    
    print(f"JSON 파일 저장됨: {output_file}")
    print(f"\n추출 완료! 총 {len(pages_data)}개 페이지가 {output_file}에 저장되었습니다.")
    
    return pages_data


def main():
    parser = argparse.ArgumentParser(description="PDF를 페이지별로 JSON으로 추출")
    parser.add_argument("pdf_path", help="PDF 파일 경로")
    parser.add_argument("-o", "--output", help="출력 JSON 파일명 (기본값: PDF_이름.json)")
    
    args = parser.parse_args()
    
    try:
        pages_data = extract_pdf_pages(args.pdf_path, args.output)
        
        # 간단한 통계 출력
        total_text_length = sum(len(text) for text in pages_data.values())
        print(f"\n통계:")
        print(f"- 총 페이지 수: {len(pages_data)}")
        print(f"- 총 텍스트 길이: {total_text_length:,} 문자")
        print(f"- 평균 페이지당 텍스트 길이: {total_text_length // len(pages_data):,} 문자")
        
    except Exception as e:
        print(f"오류 발생: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
