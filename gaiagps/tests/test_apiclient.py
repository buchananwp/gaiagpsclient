import http.cookiejar
import mock
import os
import tempfile
import unittest

from gaiagps import apiclient
from gaiagps import util


TEST_NAME_BASE = 'gaiagpsclient test data'


def test_name(slug):
    return '%s %s' % (TEST_NAME_BASE, slug)


SAMPLE_GPX = ''.join([
    '<?xml version="1.0" ?><gpx creator="GaiaGPS" version="1.1" '
    'xmlns="http://www.topografix.com/GPX/1/1" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://www.topografix.com/GPX/1/1 '
    'http://www.topografix.com/GPX/1/1/gpx.xsd">'
    '<wpt lat="45.5" lon="-122.9"><ele>123</ele>'
    '<time>2019-04-19T00:38:03Z</time><name>%s</name></wpt>'
    '</gpx>'])


class TestClientUnit(unittest.TestCase):
    def setUp(self):
        self.request_mock = mock.patch('requests.Session')
        session_mock = self.request_mock.start()
        self.requests = session_mock.return_value

    def tearDown(self):
        self.request_mock.stop()

    @mock.patch('gaiagps.apiclient.GaiaClient.test_auth')
    def test_login(self, mock_test_auth):
        mock_test_auth.return_value = False
        self.requests.post.return_value.status_code = 200
        self.requests.post.return_value.url = '/something'
        apiclient.GaiaClient('foo', 'bar')
        self.requests.post.assert_called_once_with(
            apiclient.gurl('login/'),
            data={'username': 'foo', 'password': 'bar', 'next': '/'})

    @mock.patch('gaiagps.apiclient.GaiaClient.test_auth')
    def test_login_failure(self, mock_test_auth):
        mock_test_auth.return_value = False
        self.requests.post.return_value.status_code = 200
        self.requests.post.return_value.url = '/login'
        self.assertRaises(apiclient.AuthFailure,
                          apiclient.GaiaClient, 'foo', 'bar')

        self.requests.post.return_value.status_code = 400
        self.requests.post.return_value.url = '/something'
        self.assertRaises(apiclient.AuthFailure,
                          apiclient.GaiaClient, 'foo', 'bar')

    @mock.patch('gaiagps.apiclient.GaiaClient.test_auth')
    def test_login_not_needed(self, mock_test_auth):
        mock_test_auth.return_value = True
        self.requests.post.assert_not_called()

    @mock.patch('gaiagps.apiclient.GaiaClient.test_auth')
    def get_api(self, mock_test_auth):
        mock_test_auth.return_value = True
        return apiclient.GaiaClient('foo', 'bar')

    def test_get_object(self):
        api = self.get_api()

        with mock.patch.object(api, 'list_objects') as mock_list:
            mock_list.return_value = [
                {'id': '1', 'title': 'urpoint'},
                {'id': '2', 'title': 'mypoint'},
            ]

            # Get in JSON format
            obj = api.get_object('waypoint', 'mypoint')
            self.assertEqual(self.requests.get.return_value.json.return_value,
                             obj)
            self.requests.get.assert_called_once_with(
                apiclient.gurl('api', 'objects', 'waypoint', '2'))

            self.requests.get.reset_mock()

            # Get in GPX format
            obj = api.get_object('waypoint', 'mypoint', fmt='gpx')
            self.assertEqual(self.requests.get.return_value.content,
                             obj)
            self.requests.get.assert_called_once_with(
                apiclient.gurl('api', 'objects', 'waypoint', '2.gpx'))

    def test_get_object_failures(self):
        api = self.get_api()

        self.assertRaises(RuntimeError,
                          api.get_object, 'waypoint')
        self.assertRaises(AssertionError,
                          api.get_object, 'waypoint', id_='foo', fmt='png')
        self.assertRaises(apiclient.NotFound,
                          api.get_object, 'waypoint', name='foo')

    def test_create_object(self):
        api = self.get_api()

        obj = api.create_object('waypoint', {'name': 'foo'})
        self.assertEqual(self.requests.post.return_value.json.return_value,
                         obj)
        self.requests.post.assert_called_once_with(
            apiclient.gurl('api', 'objects', 'waypoint/'),
            json={'name': 'foo'})

    def test_put_object(self):
        api = self.get_api()

        self.requests.put.return_value.status_code = 201
        obj = api.put_object('waypoint', {'name': 'foo', 'id': '1'})
        self.assertEqual(self.requests.put.return_value.json.return_value,
                         obj)
        self.requests.put.assert_called_once_with(
            apiclient.gurl('api', 'objects', 'waypoint', '1/'),
            json={'name': 'foo', 'id': '1'})

        self.requests.put.return_value.status_code = 202
        obj = api.put_object('waypoint', {'name': 'foo', 'id': '1'})
        self.assertTrue(obj)

        self.requests.put.return_value.status_code = 400
        obj = api.put_object('waypoint', {'name': 'foo', 'id': '1'})
        self.assertIsNone(obj)

    def test_delete_object(self):
        api = self.get_api()

        r = api.delete_object('waypoint', '1')
        self.assertIsNone(r)
        self.requests.delete.assert_called_once_with(
            apiclient.gurl('api', 'objects', 'waypoint', '1'))

    def test_add_object_to_folder(self):
        api = self.get_api()

        with mock.patch.object(api, 'list_objects') as mock_list:
            self.requests.put.return_value.status_code = 201
            mock_list.return_value = [
                {'id': 'folder1', 'name': 'My Folder',
                 'waypoints': ['2'], 'children': []},
                {'id': 'folder2', 'name': 'Other Folder'},
            ]

            # Add a waypoint
            folder = api.add_object_to_folder(
                'folder1', 'waypoint', 'waypoint1')
            self.assertEqual(self.requests.put.return_value.json.return_value,
                             folder)
            self.requests.put.assert_called_once_with(
                apiclient.gurl('api', 'objects', 'folder', 'folder1/'),
                json={'id': 'folder1', 'name': 'My Folder',
                      'children': [],
                      'waypoints': ['2', 'waypoint1']})

            self.requests.put.reset_mock()

            # Add another folder
            folder = api.add_object_to_folder(
                'folder1', 'folder', 'folder2')
            self.assertEqual(self.requests.put.return_value.json.return_value,
                             folder)
            self.requests.put.assert_called_once_with(
                apiclient.gurl('api', 'objects', 'folder', 'folder1/'),
                json={'id': 'folder1', 'name': 'My Folder',
                      'children': ['folder2'],
                      'waypoints': ['2', 'waypoint1']})

    def test_add_object_to_folder_failures(self):
        api = self.get_api()

        self.assertRaises(AssertionError,
                          api.add_object_to_folder, 'foo', 'image', 'bar')

        self.assertRaises(apiclient.NotFound,
                          api.add_object_to_folder, 'none', 'waypoint', '1')

    def test_remove_object_from_folder(self):
        api = self.get_api()

        with mock.patch.object(api, 'list_objects') as mock_list:
            self.requests.put.return_value.status_code = 201
            mock_list.return_value = [
                {'id': 'folder1', 'name': 'My Folder',
                 'waypoints': ['2'], 'children': ['folder2']},
                {'id': 'folder2', 'name': 'Other Folder'},
            ]

            # Remove a waypoint
            folder = api.remove_object_from_folder('folder1', 'waypoint', '2')
            self.assertEqual(self.requests.put.return_value.json.return_value,
                             folder)
            self.requests.put.assert_called_once_with(
                apiclient.gurl('api', 'objects', 'folder', 'folder1/'),
                json={'id': 'folder1', 'name': 'My Folder',
                      'children': ['folder2'],
                      'waypoints': []})

            self.requests.put.reset_mock()

            # Remove a folder
            folder = api.remove_object_from_folder(
                'folder1', 'folder', 'folder2')
            self.assertEqual(self.requests.put.return_value.json.return_value,
                             folder)
            self.requests.put.assert_called_once_with(
                apiclient.gurl('api', 'objects', 'folder', 'folder1/'),
                json={'id': 'folder1', 'name': 'My Folder',
                      'children': [],
                      'waypoints': []})

    def test_remove_object_from_folder_failures(self):
        api = self.get_api()

        self.assertRaises(AssertionError,
                          api.remove_object_from_folder, 'foo', 'image', 'bar')

        self.assertRaises(apiclient.NotFound,
                          api.remove_object_from_folder,
                          'none', 'waypoint', '1')

    @mock.patch('builtins.open')
    def test_upload(self, mock_open):
        api = self.get_api()

        self.requests.post.return_value.url = '/foo/newfolderid/'
        with mock.patch.object(api, 'get_object') as mock_get:
            folder = api.upload_file('path/to/foo.gpx')
            self.assertEqual(mock_get.return_value, folder)
            mock_get.assert_called_once_with('folder', id_='newfolderid')
            self.requests.post.assert_called_once_with(
                apiclient.gurl('upload/'),
                files={'files': mock_open.return_value},
                data={'name': 'foo.gpx'},
                allow_redirects=True)
            mock_open.assert_called_once_with('path/to/foo.gpx', 'rb')


class TestClientFunctional(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Transient cookie jar, once per test invocation
        cls.cookies = http.cookiejar.LWPCookieJar()

    def setUp(self):
        try:
            username = os.environ['GAIA_USER']
            password = os.environ['GAIA_PASS']
        except KeyError:
            raise Exception('Specify gaia credentials in '
                            'GAIA_USER and GAIA_PASS environment variables')

        self.api = apiclient.GaiaClient(username, password,
                                        cookies=self.cookies)

        # Clean up from any previous runs
        self._clean(verbose=True)

    def tearDown(self):
        # Avoid warnings from unittest about unclosed sockets
        self.api.s.close()

    def _clean(self, verbose=False):
        types = ('folder', 'waypoint', 'track')

        for objtype in types:
            objs = self.api.list_objects(objtype)
            for obj in objs:
                if obj['title'].startswith(TEST_NAME_BASE):
                    self.api.delete_object(objtype, obj['id'])
                    if verbose:
                        print('Cleaning stale %s %s/%s' % (objtype,
                                                           obj['id'],
                                                           obj['title']))

    def test_test_auth(self):
        self.assertTrue(self.api.test_auth())

    def test_create_delete_folder(self):
        name = test_name('folder')
        folder = self.api.create_object('folder', util.make_folder(name))
        self.assertIn('id', folder)
        self.assertEqual(name, folder['properties']['name'])
        folders = self.api.list_objects('folder')
        the_folder = apiclient.find(folders, 'id', folder['id'])
        self.assertEqual(name, the_folder['title'])
        self.assertEqual(folder['id'], the_folder['id'])
        self._clean()

    def test_create_waypoint(self):
        name = test_name('waypoint')
        wpt = self.api.create_object('waypoint',
                                     util.make_waypoint(name, 45.0, -122.0))
        self.assertIn('id', wpt)
        self.assertEqual(name, wpt['properties']['title'])
        waypoints = self.api.list_objects('waypoint')
        the_wpt = apiclient.find(waypoints, 'id', wpt['id'])
        self.assertEqual(name, the_wpt['title'])
        self.assertEqual(wpt['id'], the_wpt['id'])
        self._clean()

    def test_folder_move_ops(self):
        test_objs = {}
        for i, name in enumerate(['wpt1', 'wpt2']):
            wpt = self.api.create_object('waypoint',
                                         util.make_waypoint(
                                             test_name(name),
                                             45.0 + i, -122.0 - i))
            test_objs[name] = wpt
        for name in ('folder', 'subfolder'):
            fld = self.api.create_object('folder',
                                         util.make_folder(test_name(name)))
            test_objs[name] = fld

        self.api.add_object_to_folder(test_objs['folder']['id'],
                                      'waypoint',
                                      test_objs['wpt1']['id'])
        self.api.add_object_to_folder(test_objs['subfolder']['id'],
                                      'waypoint',
                                      test_objs['wpt2']['id'])

        # Make sure the waypoints are in their respective folders
        folders = self.api.list_objects('folder')
        folder = apiclient.find(folders, 'id', test_objs['folder']['id'])
        self.assertEqual([test_objs['wpt1']['id']], folder['waypoints'])
        subfolder = apiclient.find(folders, 'id', test_objs['subfolder']['id'])
        self.assertEqual([test_objs['wpt2']['id']], subfolder['waypoints'])

        self.api.add_object_to_folder(test_objs['folder']['id'],
                                      'folder',
                                      test_objs['subfolder']['id'])

        # Make sure the waypoints are in their respective folders, and that
        # the subfolder is in the main folder
        folders = self.api.list_objects('folder')
        folder = apiclient.find(folders, 'id', test_objs['folder']['id'])
        self.assertEqual([test_objs['wpt1']['id']], folder['waypoints'])
        self.assertEqual([test_objs['subfolder']['id']], folder['children'])
        subfolder = apiclient.find(folders, 'id', test_objs['subfolder']['id'])
        self.assertEqual([test_objs['wpt2']['id']], subfolder['waypoints'])

        # Move a waypoint out of its folder
        self.api.remove_object_from_folder(test_objs['subfolder']['id'],
                                           'waypoint',
                                           test_objs['wpt2']['id'])
        folders = self.api.list_objects('folder')
        subfolder = apiclient.find(folders, 'id', test_objs['subfolder']['id'])
        self.assertEqual([], subfolder['waypoints'])

        # Delete the top-level folder and make sure everything is gone,
        # not including wpt2, which was moved out to the root
        self.api.delete_object('folder', test_objs['folder']['id'])
        folders = self.api.list_objects('folder')
        self.assertRaises(apiclient.NotFound,
                          apiclient.find,
                          folders, 'id', test_objs['folder']['id'])
        self.assertRaises(apiclient.NotFound,
                          apiclient.find,
                          folders, 'id', test_objs['subfolder']['id'])
        waypoints = self.api.list_objects('waypoint')
        self.assertRaises(apiclient.NotFound,
                          apiclient.find,
                          waypoints, 'id', test_objs['wpt1']['id'])
        wpt2 = apiclient.find(waypoints, 'id', test_objs['wpt2']['id'])
        self.api.delete_object('waypoint', wpt2['id'])

    def test_upload_file(self):
        tmpdir = tempfile.mkdtemp()
        filename = test_name('file.gpx')
        path = os.path.join(tmpdir, filename)
        waypoint_name = test_name('point')
        with open(path, 'w') as f:
            f.write(SAMPLE_GPX % waypoint_name)

        new_folder = self.api.upload_file(path)

        # I don't understand the distinction between these structures
        folders = self.api.list_objects('folder')
        new_folder = apiclient.find(folders, 'id', new_folder['id'])

        waypoints = self.api.list_objects('waypoint')
        waypoint = apiclient.find(waypoints, 'title', waypoint_name)
        self.assertIn(waypoint['id'], new_folder['waypoints'])
        self.api.delete_object('folder', new_folder['id'])
