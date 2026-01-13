"""
Jira Service cho việc tạo và cập nhật issues
"""
import re
import logging
import unicodedata
import time
from typing import Optional, List
import requests

from config.settings import settings
from models.task_info import TaskInfo

logger = logging.getLogger(__name__)

class JiraService:
    def __init__(self):
        self.jira = None
        try:
            try:
                from jira import JIRA
            except ModuleNotFoundError:
                logger.error("❌ Python package 'jira' not installed. Install with 'pip install jira' to enable Jira integration.")
                self.jira = None
            else:
                self.jira = JIRA(server=settings.JIRA_SERVER, token_auth=settings.JIRA_API_TOKEN)
            logger.info("✅ Kết nối Jira thành công.")
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối Jira: {e}")
        if not settings.JIRA_PROJECT_KEY:
            logger.error("❌ JIRA_PROJECT_KEY chưa được cấu hình (env JIRA_PROJECT_KEY is empty). Create issue will fail.")
    
    def create_issue(self, task_info: TaskInfo):
        """
        Tạo issue mới trên Jira (minimal fields để nhanh)
        Returns: issue object
        """
        if not self.jira:
            raise Exception("Jira client chưa được khởi tạo")
        
        if not settings.JIRA_PROJECT_KEY:
            logger.error("❌ Không thể tạo issue: JIRA_PROJECT_KEY chưa được cấu hình.")
            raise ValueError("JIRA_PROJECT_KEY is required but not set in environment")

        issue_dict = {
            'project': {'key': settings.JIRA_PROJECT_KEY},
            'issuetype': {'name': task_info.issuetype}
        }
        
        # Thêm các field cơ bản
        try:
            issue_dict['summary'] = task_info.summary
            issue_dict['description'] = task_info.description
            
            # Priority - chỉ set nếu AI đã detect
            if task_info.priority:
                issue_dict['priority'] = {'name': task_info.priority}

            # Nếu có epic_link, thử set ngay khi tạo issue (sử dụng một số field IDs phổ biến)
            if task_info.epic_link:
                common_epic_fields = [
                    'customfield_10014',
                    'customfield_10102',
                    'customfield_10011',
                    'customfield_10016',
                    'customfield_10020',
                ]
                # Thử đặt giá trị epic key dưới dạng chuỗi cho mỗi field phổ biến
                for ef in common_epic_fields:
                    try:
                        issue_dict[ef] = task_info.epic_link
                        # Chỉ thêm một field đầu tiên khả dĩ
                        break
                    except Exception:
                        continue
            
            # Due date
            if task_info.due_date:
                issue_dict['duedate'] = task_info.due_date
            
        except Exception as e:
            logger.warning(f"⚠️ Không thể thêm một số fields: {e}")
        
        # Nếu là Epic, bắt buộc phải có Epic Name
        if task_info.issuetype == 'Epic':
            try:
                issue_dict['customfield_10104'] = task_info.summary
            except:
                pass
        
        try:
            new_issue = self.jira.create_issue(fields=issue_dict)
            
            # Xử lý media attachments nếu có
            if task_info.media_urls:
                self._add_media_attachments(new_issue, task_info.media_urls)
            
            return new_issue
        except Exception as e:
            error_str = str(e)
            if 'cannot be set' in error_str or 'not on the appropriate screen' in error_str:
                logger.warning(f"⚠️ Một số fields không được phép, thử với minimal fields...")
                # Nếu một số fields không được phép khi tạo, thử tạo với minimal fields
                # NOTE: Jira often requires 'summary' on create; include it to avoid HTTP 400
                minimal_dict = {
                    'project': {'key': settings.JIRA_PROJECT_KEY},
                    'issuetype': {'name': task_info.issuetype},
                    'summary': task_info.summary or 'No summary'
                }
                # Nếu có description, include luôn để tránh update step failing on some boards
                if task_info.description:
                    minimal_dict['description'] = task_info.description

                try:
                    new_issue = self.jira.create_issue(fields=minimal_dict)
                except Exception as e_min:
                    logger.warning(f"⚠️ Tạo issue minimal cũng thất bại: {e_min}")
                    raise

                # Update thêm các fields nếu cần (đảm bảo không bị bỏ sót)
                update_fields = {}
                if task_info.summary and task_info.summary != getattr(new_issue.fields, 'summary', None):
                    update_fields['summary'] = task_info.summary
                if task_info.description and task_info.description != getattr(new_issue.fields, 'description', None):
                    update_fields['description'] = task_info.description
                if update_fields:
                    try:
                        new_issue.update(fields=update_fields)
                    except Exception as e2:
                        logger.warning(f"⚠️ Không thể update fields sau khi tạo: {e2}")

                return new_issue
            else:
                raise
    
    def update_issue(self, issue_key: str, task_info: TaskInfo, epic_issue=None):
        """
        Cập nhật issue với thông tin bổ sung (background task)
        Xử lý từng field riêng biệt để nếu một field fail thì các field khác vẫn được update
        """
        logger.info(f"🔄 Bắt đầu cập nhật {issue_key}")
        
        try:
            issue = self.jira.issue(issue_key)
            update_fields = {}
            failed_fields = []
            
            # 1. Gắn epic link - thử nhiều field IDs và formats
            if task_info.epic_link:
                # Đợi một chút để đảm bảo epic đã được tạo và index
                time.sleep(2)
                epic_field_ids = self._find_all_epic_link_fields(issue)

                # Prepare formats to try. If the provided epic_link looks like a key (PROJ-123),
                # try the key and {'key': key} first — this allows linking to a just-created epic.
                formats_to_try = []
                if re.match(r'^[A-Z]+-\d+$', str(task_info.epic_link)):
                    formats_to_try.extend([
                        str(task_info.epic_link),
                        {'key': str(task_info.epic_link)}
                    ])

                # Try to resolve epic object to get numeric id if possible
                epic_obj = epic_issue
                if not epic_obj:
                    try:
                        epic_obj = self.find_epic(task_info.epic_link)
                    except Exception:
                        epic_obj = None

                if epic_obj:
                    logger.info(f"✅ Đã tìm thấy epic: {epic_obj.key} - {epic_obj.fields.summary}")
                    formats_to_try.extend([
                        epic_obj.key,
                        {'key': epic_obj.key},
                        {'id': epic_obj.id}
                    ])

                # Remove duplicates while preserving order
                seen = set()
                uniq_formats = []
                for f in formats_to_try:
                    key = str(f) if not isinstance(f, dict) else str(f.get('key') or f.get('id'))
                    if key not in seen:
                        seen.add(key)
                        uniq_formats.append(f)

                epic_set = False
                for epic_field_id in epic_field_ids:
                    if epic_set:
                        break
                    for fmt in uniq_formats:
                        try:
                            test_fields = {epic_field_id: fmt}
                            issue.update(fields=test_fields)
                            logger.info(f"✅ Đã set epic link {task_info.epic_link} với field {epic_field_id}")
                            epic_set = True
                            break
                        except Exception as e:
                            error_str = str(e).lower()
                            if 'cannot be set' in error_str or 'not on the appropriate screen' in error_str:
                                logger.debug(f"⚠️ Field {epic_field_id} không thể set epic link: {e}")
                                continue
                            else:
                                continue

                if not epic_set:
                    logger.warning(f"⚠️ Không thể set epic link {task_info.epic_link} cho {issue_key} (đã thử {len(epic_field_ids)} field IDs)")
                    failed_fields.append('epic_link')
            
            # 2. Gắn assignee
            if task_info.assignee:
                user = self._find_user(task_info.assignee)
                if user:
                    assignee_formats = []
                    
                    if hasattr(user, 'accountId') and user.accountId:
                        assignee_formats.append({'accountId': user.accountId})
                    if hasattr(user, 'name') and user.name:
                        assignee_formats.append({'name': user.name})
                    
                    assignee_set = False
                    for fmt in assignee_formats:
                        try:
                            test_fields = {'assignee': fmt}
                            issue.update(fields=test_fields)
                            logger.info(f"✅ Đã set assignee: {user.displayName if hasattr(user, 'displayName') else user.name}")
                            assignee_set = True
                            break
                        except Exception as e:
                            logger.warning(f"⚠️ Thử set assignee với {fmt} thất bại: {e}")
                            continue
                    
                    if not assignee_set:
                        logger.warning(f"⚠️ Không thể set assignee cho {issue_key} (đã thử {len(assignee_formats)} formats)")
                        failed_fields.append('assignee')
            
            # 3. Cập nhật priority
            if task_info.priority:
                try:
                    test_fields = {'priority': {'name': task_info.priority}}
                    issue.update(fields=test_fields)
                    logger.info(f"✅ Đã set priority: {task_info.priority}")
                except Exception as e:
                    logger.warning(f"⚠️ Không thể set priority: {e}")
                    failed_fields.append('priority')
            
            # 4. Cập nhật start date
            if task_info.start_date:
                start_date_set = False
                start_date_fields = ['startDate', 'customfield_10015', 'customfield_10016']
                for field_id in start_date_fields:
                    try:
                        test_fields = {field_id: task_info.start_date}
                        issue.update(fields=test_fields)
                        logger.info(f"✅ Đã set start date: {task_info.start_date} với field {field_id}")
                        start_date_set = True
                        break
                    except Exception:
                        continue
                
                if not start_date_set:
                    logger.warning(f"⚠️ Không thể set start date cho {issue_key}")
                    failed_fields.append('start_date')
            
            # 5. Cập nhật due date
            if task_info.due_date:
                try:
                    test_fields = {'duedate': task_info.due_date}
                    issue.update(fields=test_fields)
                    logger.info(f"✅ Đã set due date: {task_info.due_date}")
                except Exception as e:
                    logger.warning(f"⚠️ Không thể set due date: {e}")
                    failed_fields.append('due_date')
            
            # 6. Thêm attachments (media URLs)
            if task_info.media_urls:
                try:
                    self._add_media_attachments(issue, task_info.media_urls)
                except Exception as e:
                    logger.warning(f"⚠️ Không thể thêm media attachments: {e}")
                    failed_fields.append('media_urls')
            
            if failed_fields:
                logger.warning(f"⚠️ Một số fields không thể cập nhật cho {issue_key}: {', '.join(failed_fields)}")
            else:
                logger.info(f"✅ Đã cập nhật thành công tất cả fields cho {issue_key}")
            
        except Exception as e:
            logger.error(f"❌ Lỗi khi cập nhật issue {issue_key}: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def find_epic(self, epic_identifier: str):
        """Tìm epic trong Jira theo key hoặc name"""
        if not epic_identifier or not self.jira:
            return None
        
        epic_identifier = epic_identifier.strip()
        
        try:
            # Extract possible key from the identifier
            possible_keys = re.findall(r'\b([A-Z]+-\d+)\b', epic_identifier)
            
            # Nếu là epic key - thử nhiều lần vì Jira có thể chưa index ngay lập tức
            if re.match(r'^[A-Z]+-\d+$', epic_identifier):
                for attempt in range(3):
                    try:
                        epic = self.jira.issue(epic_identifier)
                        if epic and hasattr(epic.fields, 'issuetype') and epic.fields.issuetype.name == 'Epic':
                            logger.info(f"✅ Tìm thấy epic theo key: {epic.key}")
                            return epic
                    except Exception as e:
                        logger.warning(f"⚠️ Attempt {attempt + 1} failed to get issue {epic_identifier}: {e}")
                        # Chờ một chút rồi thử lại
                        if attempt < 2:
                            time.sleep(1)
                        continue
            
            # Try extracted keys
            for key in possible_keys:
                for attempt in range(3):
                    try:
                        epic = self.jira.issue(key)
                        if epic and hasattr(epic.fields, 'issuetype') and epic.fields.issuetype.name == 'Epic':
                            logger.info(f"✅ Tìm thấy epic theo extracted key: {epic.key}")
                            return epic
                    except Exception as e:
                        logger.warning(f"⚠️ Attempt {attempt + 1} failed to get extracted key {key}: {e}")
                        if attempt < 2:
                            time.sleep(1)
                        continue
            
            # Tìm theo name - thử nhiều cách
            epic_normalized = epic_identifier.upper().replace('-', '').replace('_', '')
            
            # Remove common prefixes like [Ưu tiên thấp], [High], etc.
            clean_name = re.sub(r'^\s*\[.*?\]\s*', '', epic_identifier).strip()
            clean_name_normalized = clean_name.upper().replace('-', '').replace('_', '')
            
            search_queries = [
                f'issuetype = Epic AND summary ~ "{epic_identifier}"',
                f'issuetype = Epic AND summary ~ "{clean_name}"',
                f'issuetype = Epic AND summary ~ "{epic_normalized}"',
                f'issuetype = Epic AND summary ~ "{clean_name_normalized}"',
                f'project = {settings.JIRA_PROJECT_KEY} AND issuetype = Epic AND summary ~ "{epic_identifier}"',
                f'project = {settings.JIRA_PROJECT_KEY} AND issuetype = Epic AND summary ~ "{clean_name}"',
            ]
            
            for jql in search_queries:
                try:
                    epics = self.jira.search_issues(jql, maxResults=10)
                    if epics:
                        for epic in epics:
                            epic_summary_upper = epic.fields.summary.upper().replace('-', '').replace('_', '')
                            # Check various matches
                            if (epic_normalized in epic_summary_upper or 
                                epic_identifier.upper() in epic.fields.summary.upper() or
                                clean_name_normalized in epic_summary_upper or
                                clean_name.upper() in epic.fields.summary.upper()):
                                logger.info(f"✅ Tìm thấy epic: {epic.key} - {epic.fields.summary}")
                                return epic
                        # If no exact match, return first result
                        logger.info(f"✅ Tìm thấy possible epic: {epics[0].key} - {epics[0].fields.summary}")
                        return epics[0]
                except Exception as e:
                    logger.warning(f"⚠️ JQL failed: {jql} - {e}")
                    continue
            
            logger.warning(f"⚠️ Không tìm thấy epic: {epic_identifier}")
            return None
        except Exception as e:
            logger.error(f"❌ Lỗi khi tìm epic: {e}")
            return None
    
    def _find_epic_link_field_id(self, issue):
        """Tìm field ID của epic link (giữ lại để backward compatibility)"""
        fields = self._find_all_epic_link_fields(issue)
        return fields[0] if fields else 'customfield_10014'
    
    def _find_all_epic_link_fields(self, issue):
        """Tìm tất cả các field IDs có thể là epic link field"""
        epic_field_ids = []
        issue_fields = issue.raw['fields']
        
        # Danh sách các field IDs phổ biến cho epic link
        common_epic_fields = [
            'customfield_10014',  # Phổ biến nhất
            'customfield_10011',
            'customfield_10016',
            'customfield_10020',
            'customfield_10104',
            'customfield_10010',
            'customfield_10013',
        ]
        
        # Kiểm tra các field có trong issue
        for field_id in common_epic_fields:
            if field_id in issue_fields:
                epic_field_ids.append(field_id)
        
        # Nếu không tìm thấy, thử tìm trong danh sách fields của Jira
        if not epic_field_ids:
            try:
                fields = self.jira.fields()
                for field in fields:
                    field_name_lower = field.get('name', '').lower()
                    if any(keyword in field_name_lower for keyword in ['epic link', 'parent link', 'epic']):
                        field_id = field.get('id')
                        if field_id and field_id not in epic_field_ids:
                            epic_field_ids.append(field_id)
            except Exception as e:
                logger.debug(f"⚠️ Không thể lấy danh sách fields từ Jira: {e}")
        
        # Nếu vẫn không tìm thấy, trả về field phổ biến nhất để thử
        if not epic_field_ids:
            epic_field_ids = ['customfield_10014']
        
        logger.debug(f"🔍 Found epic field IDs: {epic_field_ids}")
        return epic_field_ids
    
    def _find_user(self, assignee: str):
        """Tìm user trên Jira"""
        assignee_clean = assignee.replace('\xa0', ' ').replace('\u00a0', ' ')
        assignee_clean = re.sub(r'\s*\([^)]+\)', '', assignee_clean).strip()
        assignee_clean = re.sub(r'\s+', ' ', assignee_clean)
        
        try:
            search_queries = [assignee_clean, assignee]
            
            name_parts = assignee_clean.split()
            if len(name_parts) > 1:
                if len(name_parts) >= 2:
                    search_queries.append(f"{name_parts[0]} {name_parts[1]}")
                search_queries.append(name_parts[-1])
            
            def remove_accents(text):
                nfd = unicodedata.normalize('NFD', text)
                return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
            
            assignee_no_accent = remove_accents(assignee_clean).lower()
            if assignee_no_accent != assignee_clean.lower():
                search_queries.append(assignee_no_accent)
            
            search_queries = list(dict.fromkeys(search_queries))
            
            users = []
            for query in search_queries:
                try:
                    users = self.jira.search_users(query, maxResults=10)
                    if users:
                        break
                except:
                    continue
            
            if users:
                matched_user = None
                assignee_lower = assignee_clean.lower().strip()
                assignee_no_accent = remove_accents(assignee_lower)
                
                for user in users:
                    if hasattr(user, 'displayName') and user.displayName:
                        user_display_clean = re.sub(r'\s*\([^)]+\)', '', user.displayName).strip()
                        user_display_clean = user_display_clean.replace('\xa0', ' ')
                        user_display_lower = user_display_clean.lower()
                        user_display_no_accent = remove_accents(user_display_lower)
                        
                        if (assignee_lower == user_display_lower or 
                            assignee_no_accent == user_display_no_accent or
                            assignee_lower in user_display_lower):
                            matched_user = user
                            logger.info(f"✅ Tìm thấy user: {user.displayName}")
                            break
                
                if not matched_user and users:
                    matched_user = users[0]
                    logger.info(f"✅ Lấy user đầu tiên: {matched_user.displayName if hasattr(matched_user, 'displayName') else matched_user.name}")
                
                return matched_user
            
            logger.error(f"❌ Không tìm thấy user: {assignee}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Lỗi khi tìm user: {e}")
            return None
    
    def _add_media_attachments(self, issue, media_urls: List[str]):
        """
        Thêm media URLs vào issue
        - Download và attach files nếu có thể (ảnh và video)
        - Thêm URLs vào comment
        """
        if not media_urls:
            return
        
        logger.info(f"📎 Thêm {len(media_urls)} media URLs vào {issue.key}")
        
        # Thêm URLs vào comment
        media_text = "\n\n**📎 Media Files:**\n"
        for i, url in enumerate(media_urls, 1):
            media_text += f"{i}. {url}\n"
        
        attached_files = []
        failed_urls = []
        
        try:
            # Thử download và attach cả ảnh và video
            for url in media_urls:
                try:
                    # Download images và videos (MP4, MOV, WebM)
                    is_image = any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])
                    is_video = any(ext in url.lower() for ext in ['.mp4', '.mov', '.webm', '.avi'])
                    
                    if is_image or is_video:
                        # Set timeout dài hơn cho video
                        timeout = 30 if is_video else 10
                        
                        # Download file
                        response = requests.get(url, timeout=timeout, stream=True)
                        if response.status_code == 200:
                            # Get filename from URL
                            filename = url.split('/')[-1].split('?')[0]
                            if not filename or len(filename) > 100:
                                ext = '.mp4' if is_video else '.jpg'
                                filename = f"media_{media_urls.index(url)}{ext}"
                            
                            # Check file size (limit to 50MB)
                            content_length = response.headers.get('content-length')
                            if content_length and int(content_length) > 50 * 1024 * 1024:
                                logger.warning(f"⚠️ File quá lớn (>50MB): {filename}")
                                failed_urls.append(url)
                                continue
                            
                            # Upload to Jira using BytesIO
                            from io import BytesIO
                            file_data = BytesIO(response.content)
                            self.jira.add_attachment(issue=issue, attachment=file_data, filename=filename)
                            logger.info(f"✅ Đã attach file: {filename}")
                            attached_files.append(filename)
                        else:
                            logger.warning(f"⚠️ Không thể download (HTTP {response.status_code}): {url}")
                            failed_urls.append(url)
                except Exception as e:
                    logger.warning(f"⚠️ Không thể attach file từ {url}: {e}")
                    failed_urls.append(url)
            
            # Thêm comment với URLs và trạng thái
            if attached_files:
                media_text += f"\n✅ Đã attach: {', '.join(attached_files)}\n"
            if failed_urls:
                media_text += f"\n⚠️ Không thể download: {len(failed_urls)} file(s)\n"
            
            self.jira.add_comment(issue, media_text)
            logger.info(f"✅ Đã thêm media comment (attached: {len(attached_files)}, failed: {len(failed_urls)})")
            
        except Exception as e:
            logger.error(f"❌ Lỗi khi thêm media: {e}")

    def add_comment(self, issue_key: str, comment: str) -> bool:
        """Add a comment to an issue. Returns True if successful."""
        if not self.jira:
            logger.error("❌ Jira client chưa được khởi tạo (cannot add comment)")
            return False
        try:
            issue = self.jira.issue(issue_key)
            self.jira.add_comment(issue, comment)
            logger.info(f"✅ Đã thêm comment vào {issue_key}")
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi khi thêm comment vào {issue_key}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Chuyển trạng thái issue sang target_status
        Returns: True nếu thành công, False nếu thất bại
        """
        if not self.jira:
            logger.error("❌ Jira client chưa được khởi tạo")
            return False
        
        try:
            issue = self.jira.issue(issue_key)
            current_status = issue.fields.status.name
            
            # Nếu đã ở trạng thái mong muốn, không cần chuyển
            if current_status.lower() == target_status.lower():
                logger.info(f"ℹ️ Issue {issue_key} đã ở trạng thái {target_status}")
                return True
            
            # Lấy danh sách transitions có thể thực hiện
            transitions = self.jira.transitions(issue)
            
            # Tìm transition phù hợp với target_status
            target_transition = None
            for transition in transitions:
                if transition['name'].lower() == target_status.lower():
                    target_transition = transition
                    break
            
            # Nếu không tìm thấy exact match, thử tìm theo từ khóa
            if not target_transition:
                status_keywords = {
                    'in progress': ['in progress', 'start', 'begin', 'doing'],
                    'resolved': ['resolved', 'done', 'complete', 'fixed'],
                    'closed': ['closed', 'deployed', 'finished'],
                    'to do': ['to do', 'open', 'new'],
                    'in review': ['in review', 'review', 'testing']
                }
                
                keywords = status_keywords.get(target_status.lower(), [])
                for transition in transitions:
                    transition_name_lower = transition['name'].lower()
                    if any(keyword in transition_name_lower for keyword in keywords):
                        target_transition = transition
                        break
            
            if not target_transition:
                # Fallback: if target is 'in progress', try to pick first non-terminal transition
                if 'in progress' in target_status.lower():
                    for transition in transitions:
                        name_lower = transition['name'].lower()
                        if any(x in name_lower for x in ['done', 'closed', 'deploy', 'finish', 'finished']):
                            continue
                        # pick this as a fallback
                        target_transition = transition
                        logger.info(f"ℹ️ Fallback picked transition '{transition['name']}' for target 'in Progress'.")
                        break

            if target_transition:
                try:
                    self.jira.transition_issue(issue, target_transition['id'])
                    logger.info(f"✅ Đã chuyển {issue_key} từ '{current_status}' → '{target_status}' (transition: {target_transition['name']})")
                    return True
                except Exception as e:
                    logger.error(f"❌ Lỗi khi thực hiện transition: {e}")
                    return False
            else:
                logger.warning(f"⚠️ Không tìm thấy transition để chuyển {issue_key} sang '{target_status}'")
                logger.info(f"   Transitions có sẵn: {[t['name'] for t in transitions]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Lỗi khi chuyển trạng thái {issue_key}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def log_work(self, issue_key: str, time_spent: str, comment: str = None, started: str = None) -> bool:
        """
        Ghi worklog vào issue
        Args:
            issue_key: Jira issue key (e.g., PROJ-123)
            time_spent: Thời gian đã làm (format: "1h 30m", "2h", "30m")
            comment: Comment cho worklog (optional)
            started: Ngày giờ bắt đầu (format: "2024-01-15T10:00:00.000+0000", optional)
        Returns: True nếu thành công, False nếu thất bại
        """
        if not self.jira:
            logger.error("❌ Jira client chưa được khởi tạo")
            return False
        
        try:
            issue = self.jira.issue(issue_key)
            
            # Tạo worklog dict
            worklog_data = {
                'timeSpent': time_spent
            }
            
            if comment:
                worklog_data['comment'] = comment
            
            if started:
                worklog_data['started'] = started
            
            # Thêm worklog
            self.jira.add_worklog(issue, **worklog_data)
            logger.info(f"✅ Đã ghi worklog cho {issue_key}: {time_spent}" + (f" - {comment}" if comment else ""))
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi khi ghi worklog cho {issue_key}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    # Code duplicate đã được xóa - sử dụng các hàm ở trên
        """
        Thêm media URLs vào issue
        - Nếu là link public: thêm vào comment hoặc description
        - Nếu download được: attach file
        """
        if not media_urls:
            return
        
        logger.info(f"📎 Thêm {len(media_urls)} media URLs vào {issue.key}")
        
        # Thêm URLs vào comment
        media_text = "\n\n**📎 Media URLs:**\n"
        for i, url in enumerate(media_urls, 1):
            media_text += f"{i}. {url}\n"
        
        try:
            # Thử download và attach nếu là ảnh
            for url in media_urls:
                try:
                    # Chỉ download ảnh (không download video - quá lớn)
                    if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        response = requests.get(url, timeout=5, stream=True)
                        if response.status_code == 200:
                            # Get filename from URL
                            filename = url.split('/')[-1].split('?')[0]
                            if not filename or len(filename) > 100:
                                filename = f"image_{media_urls.index(url)}.jpg"
                            
                            # Upload to Jira
                            self.jira.add_attachment(issue=issue, attachment=response.raw, filename=filename)
                            logger.info(f"✅ Đã attach file: {filename}")
                except Exception as e:
                    logger.warning(f"⚠️ Không thể attach file từ {url}: {e}")
            
            # Luôn thêm comment với URLs
            self.jira.add_comment(issue, media_text)
            logger.info(f"✅ Đã thêm media URLs vào comment")
            
        except Exception as e:
            logger.error(f"❌ Lỗi khi thêm media: {e}")

    def add_comment(self, issue_key: str, comment: str) -> bool:
        """Add a comment to an issue. Returns True if successful."""
        if not self.jira:
            logger.error("❌ Jira client chưa được khởi tạo (cannot add comment)")
            return False
        try:
            issue = self.jira.issue(issue_key)
            self.jira.add_comment(issue, comment)
            logger.info(f"✅ Đã thêm comment vào {issue_key}")
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi khi thêm comment vào {issue_key}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Chuyển trạng thái issue sang target_status
        Returns: True nếu thành công, False nếu thất bại
        """
        if not self.jira:
            logger.error("❌ Jira client chưa được khởi tạo")
            return False
        
        try:
            issue = self.jira.issue(issue_key)
            current_status = issue.fields.status.name
            
            # Nếu đã ở trạng thái mong muốn, không cần chuyển
            if current_status.lower() == target_status.lower():
                logger.info(f"ℹ️ Issue {issue_key} đã ở trạng thái {target_status}")
                return True
            
            # Lấy danh sách transitions có thể thực hiện
            transitions = self.jira.transitions(issue)
            
            # Tìm transition phù hợp với target_status
            target_transition = None
            for transition in transitions:
                if transition['name'].lower() == target_status.lower():
                    target_transition = transition
                    break
            
            # Nếu không tìm thấy exact match, thử tìm theo từ khóa
            if not target_transition:
                status_keywords = {
                    'in progress': ['in progress', 'start', 'begin', 'doing'],
                    'resolved': ['resolved', 'done', 'complete', 'fixed'],
                    'closed': ['closed', 'deployed', 'finished'],
                    'to do': ['to do', 'open', 'new'],
                    'in review': ['in review', 'review', 'testing']
                }
                
                keywords = status_keywords.get(target_status.lower(), [])
                for transition in transitions:
                    transition_name_lower = transition['name'].lower()
                    if any(keyword in transition_name_lower for keyword in keywords):
                        target_transition = transition
                        break
            
            if not target_transition:
                # Fallback: if target is 'in progress', try to pick first non-terminal transition
                if 'in progress' in target_status.lower():
                    for transition in transitions:
                        name_lower = transition['name'].lower()
                        if any(x in name_lower for x in ['done', 'closed', 'deploy', 'finish', 'finished']):
                            continue
                        # pick this as a fallback
                        target_transition = transition
                        logger.info(f"ℹ️ Fallback picked transition '{transition['name']}' for target 'in Progress'.")
                        break

            if target_transition:
                try:
                    self.jira.transition_issue(issue, target_transition['id'])
                    logger.info(f"✅ Đã chuyển {issue_key} từ '{current_status}' → '{target_status}' (transition: {target_transition['name']})")
                    return True
                except Exception as e:
                    logger.error(f"❌ Lỗi khi thực hiện transition: {e}")
                    return False
            else:
                logger.warning(f"⚠️ Không tìm thấy transition để chuyển {issue_key} sang '{target_status}'")
                logger.info(f"   Transitions có sẵn: {[t['name'] for t in transitions]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Lỗi khi chuyển trạng thái {issue_key}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def log_work(self, issue_key: str, time_spent: str, comment: str = None, started: str = None) -> bool:
        """
        Ghi worklog vào issue
        Args:
            issue_key: Jira issue key (e.g., PROJ-123)
            time_spent: Thời gian đã làm (format: "1h 30m", "2h", "30m")
            comment: Comment cho worklog (optional)
            started: Ngày giờ bắt đầu (format: "2024-01-15T10:00:00.000+0000", optional)
        Returns: True nếu thành công, False nếu thất bại
        """
        if not self.jira:
            logger.error("❌ Jira client chưa được khởi tạo")
            return False
        
        try:
            issue = self.jira.issue(issue_key)
            
            # Tạo worklog dict
            worklog_data = {
                'timeSpent': time_spent
            }
            
            if comment:
                worklog_data['comment'] = comment
            
            if started:
                worklog_data['started'] = started
            
            # Thêm worklog
            self.jira.add_worklog(issue, **worklog_data)
            logger.info(f"✅ Đã ghi worklog cho {issue_key}: {time_spent}" + (f" - {comment}" if comment else ""))
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi khi ghi worklog cho {issue_key}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            