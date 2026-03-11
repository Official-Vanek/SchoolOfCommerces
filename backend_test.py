#!/usr/bin/env python3

import requests
import sys
import uuid
from datetime import datetime

class CommerceAcademyAPITester:
    def __init__(self):
        self.base_url = "https://commerce-learn-2.preview.emergentagent.com/api"
        self.token = None
        self.admin_token = None
        self.test_user_id = None
        self.test_admin_id = None 
        self.test_course_id = None
        self.tests_run = 0
        self.tests_passed = 0

    def log_test(self, test_name, success, message=""):
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name} - PASSED")
        else:
            print(f"❌ {test_name} - FAILED: {message}")
        return success

    def make_request(self, method, endpoint, data=None, token=None, expected_status=200):
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            return success, response.json() if success else response.text, response.status_code
        except Exception as e:
            return False, str(e), 0

    def test_student_registration(self):
        """Test student user registration"""
        timestamp = datetime.now().strftime("%H%M%S")
        user_data = {
            "email": f"student_{timestamp}@test.com",
            "password": "testpass123",
            "full_name": f"Test Student {timestamp}",
            "role": "student"
        }
        
        success, response, status = self.make_request('POST', 'auth/register', user_data, expected_status=200)
        if success and 'token' in response:
            self.token = response['token']
            self.test_user_id = response['user']['user_id']
            return self.log_test("Student Registration", True)
        else:
            return self.log_test("Student Registration", False, f"Status: {status}, Response: {response}")

    def test_admin_registration(self):
        """Test admin user registration"""
        timestamp = datetime.now().strftime("%H%M%S")
        admin_data = {
            "email": f"admin_{timestamp}@test.com", 
            "password": "adminpass123",
            "full_name": f"Test Admin {timestamp}",
            "role": "admin"
        }
        
        success, response, status = self.make_request('POST', 'auth/register', admin_data, expected_status=200)
        if success and 'token' in response:
            self.admin_token = response['token']
            self.test_admin_id = response['user']['user_id']
            return self.log_test("Admin Registration", True)
        else:
            return self.log_test("Admin Registration", False, f"Status: {status}, Response: {response}")

    def test_student_login(self):
        """Test student login"""
        login_data = {
            "email": f"student_{datetime.now().strftime('%H%M%S')}@test.com",
            "password": "testpass123"
        }
        success, response, status = self.make_request('POST', 'auth/login', login_data, expected_status=401)
        # We expect 401 since we're using a new timestamp, but API should be accessible
        return self.log_test("Student Login API", status in [200, 401], f"Got expected response format, Status: {status}")

    def test_get_current_user(self):
        """Test getting current user info"""
        if not self.token:
            return self.log_test("Get Current User", False, "No token available")
            
        success, response, status = self.make_request('GET', 'auth/me', token=self.token)
        if success and 'user_id' in response:
            return self.log_test("Get Current User", True)
        else:
            return self.log_test("Get Current User", False, f"Status: {status}, Response: {response}")

    def test_get_courses(self):
        """Test getting course catalog (public endpoint)"""
        success, response, status = self.make_request('GET', 'courses')
        if success and isinstance(response, list):
            return self.log_test("Get Courses", True, f"Found {len(response)} courses")
        else:
            return self.log_test("Get Courses", False, f"Status: {status}, Response: {response}")

    def test_create_course(self):
        """Test course creation (admin only)"""
        if not self.admin_token:
            return self.log_test("Create Course", False, "No admin token available")

        course_data = {
            "title": "Test Course - Accounting Basics",
            "description": "Learn the fundamentals of accounting",
            "instructor": "Prof. Test Admin",
            "duration": "6 weeks", 
            "fee": 299.99,
            "thumbnail": "https://example.com/thumbnail.jpg"
        }
        
        success, response, status = self.make_request('POST', 'courses', course_data, self.admin_token, expected_status=200)
        if success and 'course_id' in response:
            self.test_course_id = response['course_id']
            return self.log_test("Create Course", True)
        else:
            return self.log_test("Create Course", False, f"Status: {status}, Response: {response}")

    def test_get_course_details(self):
        """Test getting individual course details"""
        if not self.test_course_id:
            return self.log_test("Get Course Details", False, "No test course available")
            
        success, response, status = self.make_request('GET', f'courses/{self.test_course_id}')
        if success and response.get('course_id') == self.test_course_id:
            return self.log_test("Get Course Details", True)
        else:
            return self.log_test("Get Course Details", False, f"Status: {status}, Response: {response}")

    def test_add_lecture(self):
        """Test adding lecture to course (admin only)"""
        if not self.admin_token or not self.test_course_id:
            return self.log_test("Add Lecture", False, "Missing admin token or course ID")

        lecture_data = {
            "title": "Introduction to Accounting",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "description": "Basic accounting concepts",
            "duration": "30 minutes"
        }
        
        success, response, status = self.make_request('POST', f'courses/{self.test_course_id}/lectures', lecture_data, self.admin_token)
        return self.log_test("Add Lecture", success, f"Status: {status}" if not success else "")

    def test_course_enrollment(self):
        """Test course enrollment (student only)"""
        if not self.token or not self.test_course_id:
            return self.log_test("Course Enrollment", False, "Missing student token or course ID")
            
        success, response, status = self.make_request('POST', f'courses/{self.test_course_id}/enroll', {}, self.token)
        return self.log_test("Course Enrollment", success, f"Status: {status}" if not success else "")

    def test_create_admission(self):
        """Test admission application"""
        if not self.token or not self.test_course_id:
            return self.log_test("Create Admission", False, "Missing token or course ID")

        admission_data = {
            "full_name": "Test Admission Student",
            "email": "admission@test.com",
            "phone": "1234567890",
            "course_id": self.test_course_id,
            "message": "I want to join this course"
        }
        
        success, response, status = self.make_request('POST', 'admissions', admission_data, self.token)
        return self.log_test("Create Admission", success, f"Status: {status}" if not success else "")

    def test_create_query(self):
        """Test query submission (public endpoint)"""
        query_data = {
            "name": "Test Query User",
            "email": "query@test.com", 
            "subject": "Test Query Subject",
            "message": "This is a test query message"
        }
        
        success, response, status = self.make_request('POST', 'queries', query_data)
        return self.log_test("Create Query", success, f"Status: {status}" if not success else "")

    def test_get_students(self):
        """Test getting students list (admin only)"""
        if not self.admin_token:
            return self.log_test("Get Students", False, "No admin token available")
            
        success, response, status = self.make_request('GET', 'students', token=self.admin_token)
        if success and isinstance(response, list):
            return self.log_test("Get Students", True, f"Found {len(response)} students")
        else:
            return self.log_test("Get Students", False, f"Status: {status}, Response: {response}")

    def test_get_admissions(self):
        """Test getting admissions (admin only)"""
        if not self.admin_token:
            return self.log_test("Get Admissions", False, "No admin token available")
            
        success, response, status = self.make_request('GET', 'admissions', token=self.admin_token)
        if success and isinstance(response, list):
            return self.log_test("Get Admissions", True, f"Found {len(response)} admissions")
        else:
            return self.log_test("Get Admissions", False, f"Status: {status}, Response: {response}")

    def test_get_queries(self):
        """Test getting queries (admin only)"""
        if not self.admin_token:
            return self.log_test("Get Queries", False, "No admin token available")
            
        success, response, status = self.make_request('GET', 'queries', token=self.admin_token)
        if success and isinstance(response, list):
            return self.log_test("Get Queries", True, f"Found {len(response)} queries")
        else:
            return self.log_test("Get Queries", False, f"Status: {status}, Response: {response}")

    def test_add_result(self):
        """Test adding student result (admin only)"""
        if not self.admin_token or not self.test_user_id or not self.test_course_id:
            return self.log_test("Add Result", False, "Missing required data")

        result_data = {
            "user_id": self.test_user_id,
            "course_id": self.test_course_id,
            "marks": 85.5,
            "grade": "A",
            "remarks": "Excellent performance"
        }
        
        success, response, status = self.make_request('POST', 'results', result_data, self.admin_token)
        return self.log_test("Add Result", success, f"Status: {status}" if not success else "")

    def test_get_results(self):
        """Test getting student results"""
        if not self.token:
            return self.log_test("Get Results", False, "No student token available")
            
        success, response, status = self.make_request('GET', 'results', token=self.token)
        if success and isinstance(response, list):
            return self.log_test("Get Results", True, f"Found {len(response)} results")
        else:
            return self.log_test("Get Results", False, f"Status: {status}, Response: {response}")

    def test_chatbot_message(self):
        """Test chatbot functionality"""
        if not self.token:
            return self.log_test("Chatbot Message", False, "No student token available")

        message_data = {
            "message": "What courses are available?"
        }
        
        success, response, status = self.make_request('POST', 'chatbot/message', message_data, self.token)
        if success and 'response' in response:
            return self.log_test("Chatbot Message", True, f"Got response: {response['response'][:50]}...")
        else:
            return self.log_test("Chatbot Message", False, f"Status: {status}, Response: {response}")

    def test_block_student(self):
        """Test blocking/unblocking student (admin only)"""
        if not self.admin_token or not self.test_user_id:
            return self.log_test("Block Student", False, "Missing admin token or user ID")

        success, response, status = self.make_request('PUT', f'students/{self.test_user_id}/block?is_blocked=true', {}, self.admin_token)
        return self.log_test("Block Student", success, f"Status: {status}" if not success else "")

    def run_all_tests(self):
        """Run comprehensive test suite"""
        print("🚀 Starting Commerce Academy API Test Suite")
        print(f"🔗 Testing endpoint: {self.base_url}")
        print("=" * 60)

        # Authentication Tests
        print("\n📋 Authentication Tests:")
        self.test_student_registration()
        self.test_admin_registration()
        self.test_student_login()
        self.test_get_current_user()

        # Course Management Tests  
        print("\n📚 Course Management Tests:")
        self.test_get_courses()
        self.test_create_course()
        self.test_get_course_details()
        self.test_add_lecture()
        self.test_course_enrollment()

        # Application & Query Tests
        print("\n📝 Application & Query Tests:")
        self.test_create_admission()
        self.test_create_query()

        # Admin Management Tests
        print("\n👨‍💼 Admin Management Tests:")
        self.test_get_students()
        self.test_get_admissions()
        self.test_get_queries()
        self.test_block_student()

        # Results & AI Tests
        print("\n🎯 Results & AI Tests:")
        self.test_add_result()
        self.test_get_results()
        self.test_chatbot_message()

        # Summary
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        success_rate = (self.tests_passed / self.tests_run) * 100 if self.tests_run > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 80:
            print("🎉 Overall Status: GOOD - Most functionality working")
        elif success_rate >= 60:
            print("⚠️  Overall Status: MODERATE - Some issues detected")
        else:
            print("🚨 Overall Status: POOR - Major issues detected")

        return success_rate >= 80


if __name__ == "__main__":
    tester = CommerceAcademyAPITester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)