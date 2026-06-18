import 'dart:convert';

import 'package:http/http.dart' as http;

class EnterpriseApiClient {
  EnterpriseApiClient(this.baseUrl);

  final String baseUrl;

  Future<Map<String, dynamic>> capabilities() async {
    final response = await http.get(Uri.parse('$baseUrl/api/v1/capabilities'));
    return _decode(response);
  }

  Future<Map<String, dynamic>> listScans() async {
    final response = await http.get(Uri.parse('$baseUrl/api/v1/scans'));
    return _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode >= 400) {
      throw Exception(body['detail'] ?? 'API request failed');
    }
    return body;
  }
}
