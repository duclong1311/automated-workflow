"""
Jira Service cho việc tạo và cập nhật issues
"""
import re
import logging
import unicodedata
from typing import Optional, List
from jira import JIRA
import requests

from config.settings import settings
from models.task_info import TaskInfo

logger = logging.getLogger(__name__)

class JiraService:
    def __init__(self):
        self.jira = None
        try:
            self.jira = JIRA(server=settings.JIRA_SERVER, token_auth=settings.JIRA_API_TOKEN)
            logger.info("✅ Kết nối Jira thành công.")
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối Jira: {e}")
    
    def create_issue(self, task_info: TaskInfo):
        """
        Tạo issue mới trên Jira (minimal fields để nhanh)
        Returns: issue object
        """
        if not self.jira:
            raise Exception("Jira client chưa được khởi tạo")
        
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
            return new_issue
        except Exception as e:
            error_str = str(e)
            if 'cannot be set' in error_str or 'not on the appropriate screen' in error_str:
                logger.warning(f"⚠️ Một số fields không được phép, thử với minimal fields...")
                minimal_dict = {
                    'project': {'key': settings.JIRA_PROJECT_KEY},
                    'issuetype': {'name': task_info.issuetype}
                }
                new_issue = self.jira.create_issue(fields=minimal_dict)
                
                # Update sau
                update_fields = {}
                if task_info.summary:
                    update_fields['summary'] = task_info.summary
                if task_info.description:
                    update_fields['description'] = task_info.description
                if update_fields:
                    try:
                        new_issue.update(fields=update_fields)
                    except Exception as e2:
                        logger.warning(f"⚠️ Không thể update fields sau khi tạo: {e2}")
                
                return new_issue
            else:
                raise
    
    def update_issue(self, issue_key: str, task_info: TaskInfo):
        """
        Cập nhật issue với thông tin bổ sung (background task)
        """
        logger.info(f"🔄 Bắt đầu cập nhật {issue_key}")
        
        try:
            issue = self.jira.issue(issue_key)
            update_fields = {}
            
            # 1. Gắn epic link
            if task_info.epic_link:
                epic = self.find_epic(task_info.epic_link)
                if epic:
                    logger.info(f"✅ Đã tìm thấy epic: {epic.key} - {epic.fields.summary}")
                    epic_field_id = self._find_epic_link_field_id(issue)
                    
                    if epic_field_id:
                        formats_to_try = [
                            epic.key,
                            {'key': epic.key},
                            {'id': epic.id},
                        ]
                        
                        for fmt in formats_to_try:
                            try:
                                update_fields[epic_field_id] = fmt
                                break
                            except:
                                continue
            
            # 2. Gắn assignee
            if task_info.assignee:
                user = self._find_user(task_info.assignee)
                if user:
                    assignee_formats = []
                    
                    if hasattr(user, 'accountId') and user.accountId:
                        assignee_formats.append({'accountId': user.accountId})
                    if hasattr(user, 'name') and user.name:
                        assignee_formats.append({'name': user.name})
                    
                    for fmt in assignee_formats:
                        try:
                            update_fields['assignee'] = fmt
                            logger.info(f"✅ Đã set assignee: {user.displayName if hasattr(user, 'displayName') else user.name}")
                            break
                        except:
                            continue
            
            # 3. Cập nhật priority (nếu chưa set khi tạo)
            if task_info.priority:
                try:
                    update_fields['priority'] = {'name': task_info.priority}
                    logger.info(f"✅ Đã set priority: {task_info.priority}")
                except Exception as e:
                    logger.warning(f"⚠️ Không thể set priority: {e}")
            
            # 4. Cập nhật start date
            if task_info.start_date:
                try:
                    # Jira field cho start date thường là startDate hoặc customfield
                    # Thử nhiều field IDs phổ biến
                    start_date_fields = ['startDate', 'customfield_10015', 'customfield_10016']
                    for field_id in start_date_fields:
                        try:
                            update_fields[field_id] = task_info.start_date
                            logger.info(f"✅ Đã set start date: {task_info.start_date}")
                            break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"⚠️ Không thể set start date: {e}")
            
            # 5. Cập nhật due date
            if task_info.due_date:
                try:
                    update_fields['duedate'] = task_info.due_date
                    logger.info(f"✅ Đã set due date: {task_info.due_date}")
                except Exception as e:
                    logger.warning(f"⚠️ Không thể set due date: {e}")
            
            # 6. Cập nhật issue nếu có thay đổi
            if update_fields:
                logger.info(f"📝 Cập nhật {issue_key} với fields: {update_fields}")
                issue.update(fields=update_fields)
                logger.info(f"✅ Đã cập nhật thành công {issue_key}")
            
            # 7. Thêm attachments (media URLs)
            if task_info.media_urls:
                self._add_media_attachments(issue, task_info.media_urls)
            
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
            # Nếu là epic key
            if re.match(r'^[A-Z]+-\d+$', epic_identifier):
                try:
                    epic = self.jira.issue(epic_identifier)
                    if epic.fields.issuetype.name == 'Epic':
                        logger.info(f"✅ Tìm thấy epic theo key: {epic.key}")
                        return epic
                except:
                    pass
            
            # Tìm theo name
            epic_normalized = epic_identifier.upper().replace('-', '').replace('_', '')
            
            search_queries = [
                f'project = {settings.JIRA_PROJECT_KEY} AND issuetype = Epic AND summary ~ "{epic_identifier}"',
                f'project = {settings.JIRA_PROJECT_KEY} AND issuetype = Epic AND summary ~ "{epic_normalized}"',
            ]
            
            for jql in search_queries:
                try:
                    epics = self.jira.search_issues(jql, maxResults=10)
                    if epics:
                        for epic in epics:
                            epic_summary_upper = epic.fields.summary.upper().replace('-', '').replace('_', '')
                            if epic_normalized in epic_summary_upper or epic_identifier.upper() in epic.fields.summary.upper():
                                logger.info(f"✅ Tìm thấy epic: {epic.key}")
                                return epic
                        return epics[0]
                except:
                    continue
            
            logger.warning(f"⚠️ Không tìm thấy epic: {epic_identifier}")
            return None
        except Exception as e:
            logger.error(f"❌ Lỗi khi tìm epic: {e}")
            return None
    
    def _find_epic_link_field_id(self, issue):
        """Tìm field ID của epic link"""
        common_epic_fields = ['customfield_10014', 'customfield_10011', 'customfield_10016', 'customfield_10020', 'customfield_10104']
        issue_fields = issue.raw['fields']
        
        for field_id in common_epic_fields:
            if field_id in issue_fields:
                return field_id
        
        return 'customfield_10014'
    
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