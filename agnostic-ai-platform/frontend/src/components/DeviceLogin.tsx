import React, { useState, useEffect, useRef } from 'react';
import { QRCodeSVG } from 'qrcode.react';

interface DeviceAuthResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete: string;
  expires_in: number;
  interval: number;
}

interface DeviceTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  scope?: string;
}

const API_BASE_URL = 'http://localhost:8000'; // Replace with env var in production
const CLIENT_ID = 'frontend-client';

export const DeviceLogin: React.FC = () => {
  const [authData, setAuthData] = useState<DeviceAuthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    const fetchAuthCode = async () => {
      try {
        setLoading(true);
        const res = await fetch(`${API_BASE_URL}/auth/device/authorize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: CLIENT_ID })
        });
        
        if (!res.ok) {
          throw new Error('Failed to start device authorization');
        }

        const data: DeviceAuthResponse = await res.json();
        setAuthData(data);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchAuthCode();
  }, []);

  useEffect(() => {
    if (!authData) return;

    const pollForToken = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/auth/device/token`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: CLIENT_ID,
            device_code: authData.device_code,
            grant_type: "urn:ietf:params:oauth:grant-type:device_code"
          })
        });

        if (res.ok) {
          const data: DeviceTokenResponse = await res.json();
          setToken(data.access_token);
          if (intervalRef.current !== null) {
            window.clearInterval(intervalRef.current);
          }
        } else {
          const errData = await res.json();
          if (errData.error === 'authorization_pending') {
            // Wait for next poll
          } else {
            setError(errData.error_description || 'Authorization failed');
            if (intervalRef.current !== null) {
              window.clearInterval(intervalRef.current);
            }
          }
        }
      } catch (err: any) {
        // network issue, keep polling
      }
    };

    intervalRef.current = window.setInterval(pollForToken, authData.interval * 1000);

    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
      }
    };
  }, [authData]);

  if (token) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <h2 style={styles.title}>Login Successful!</h2>
          <p style={styles.successText}>You are now authenticated.</p>
          <div style={styles.tokenBox}>{token}</div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h2 style={styles.title}>Device Login</h2>
        
        {loading && <p style={styles.text}>Initializing login...</p>}
        {error && <p style={styles.errorText}>Error: {error}</p>}
        
        {authData && !loading && !error && (
          <div style={styles.content}>
            <p style={styles.text}>Scan the QR Code below or visit:</p>
            <a href={authData.verification_uri} target="_blank" rel="noreferrer" style={styles.link}>
              {authData.verification_uri}
            </a>
            
            <div style={styles.qrContainer}>
              <QRCodeSVG value={authData.verification_uri_complete} size={200} />
            </div>
            
            <p style={styles.text}>And enter the code:</p>
            <h1 style={styles.codeText}>{authData.user_code}</h1>
            
            <p style={styles.infoText}>Waiting for authorization...</p>
            <div style={styles.loader}></div>
          </div>
        )}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    backgroundColor: '#0f172a',
    color: '#f8fafc',
    fontFamily: "'Inter', sans-serif",
  },
  card: {
    background: 'rgba(30, 41, 59, 0.7)',
    backdropFilter: 'blur(10px)',
    borderRadius: '16px',
    padding: '40px',
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
    textAlign: 'center',
    width: '100%',
    maxWidth: '450px',
    border: '1px solid rgba(255, 255, 255, 0.1)'
  },
  title: {
    margin: '0 0 20px 0',
    fontSize: '28px',
    fontWeight: 600,
    background: 'linear-gradient(45deg, #38bdf8, #818cf8)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  text: {
    fontSize: '16px',
    color: '#cbd5e1',
    marginBottom: '10px'
  },
  link: {
    color: '#38bdf8',
    textDecoration: 'none',
    fontWeight: 500,
    fontSize: '16px',
    marginBottom: '20px',
    display: 'block'
  },
  qrContainer: {
    background: '#ffffff',
    padding: '20px',
    borderRadius: '12px',
    display: 'inline-block',
    margin: '20px 0'
  },
  codeText: {
    fontSize: '42px',
    letterSpacing: '4px',
    fontWeight: 700,
    color: '#f8fafc',
    margin: '10px 0',
    textShadow: '0 2px 10px rgba(56, 189, 248, 0.3)'
  },
  infoText: {
    fontSize: '14px',
    color: '#94a3b8',
    marginTop: '20px'
  },
  errorText: {
    color: '#ef4444',
    padding: '10px',
    background: 'rgba(239, 68, 68, 0.1)',
    borderRadius: '8px',
    border: '1px solid rgba(239, 68, 68, 0.2)'
  },
  successText: {
    color: '#10b981',
    fontSize: '18px',
    marginBottom: '20px'
  },
  tokenBox: {
    background: 'rgba(0, 0, 0, 0.3)',
    padding: '15px',
    borderRadius: '8px',
    color: '#64748b',
    fontSize: '12px',
    wordBreak: 'break-all',
    border: '1px solid rgba(255, 255, 255, 0.05)'
  },
  content: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center'
  },
  loader: {
    marginTop: '15px',
    width: '40px',
    height: '4px',
    background: 'linear-gradient(90deg, transparent, #38bdf8, transparent)',
    backgroundSize: '200% 100%',
    animation: 'loading 1.5s infinite linear',
    borderRadius: '2px'
  }
};
