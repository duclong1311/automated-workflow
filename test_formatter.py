#!/usr/bin/env python3
"""
Test script cho Jira formatter
"""
from utils.jira_formatter import auto_format_jira_description

# Test với nội dung user cung cấp
test_text = """*[Nội dung đối ứng]*
 * Đối ứng thêm cho menu khi click button 3 chấm dọc cho chat chưa được gắn project
 * Đối ứng thêm cho menu khi click button 3 chấm dọc cho chat đã được gắn project
 ** UI hiện tại: giống ảnh TH chưa gắn project
 ** Đối ứng thêm button 
 *** "プロジェクトを移動する" để move chat sang 1 project khác
 *** "プロジェクトを削除する" để remove chat khỏi project hiện tại
 * Hành vi button "プロジェクトを移動する"
 ** Khi click sẽ mở dialog chọn list project để move vào (Gọi API GET bff/v1/ChatPageBff/Init, data project ở trong data.folders)
 *** Click button "X" hoặc "キャンセル" sẽ close dialog và vẫn giữ nguyên trạng thái mở leftbar
 *** Click button "移動" sẽ move chat vào project được chọn, vẫn giữ nguyên trạng thái mở leftbar và hiển thị UI mới nhất"""

if __name__ == '__main__':
    print("=" * 80)
    print("ORIGINAL TEXT:")
    print("=" * 80)
    print(test_text)
    print()
    print("=" * 80)
    print("JIRA FORMATTED TEXT:")
    print("=" * 80)
    formatted = auto_format_jira_description(test_text)
    print(formatted)
    print()
    print("=" * 80)
    print("Copy formatted text trên và paste vào Jira description để test!")
