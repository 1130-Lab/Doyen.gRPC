using Doyen.gRPC.Algorithms;
using Doyen.Scripts.AlgorithmSharp.API;
using Doyen.Scripts.AlgorithmsSharp;
using Grpc.Core;
using System.Threading;

namespace Doyen.Scripts.AlgorithmsSharp
{
    internal class Program
    {
        static async Task Main(string[] args)
        {
            var serverAddress = GetArgument(args, "--server", "localhost:42069");
            var clientAddress = GetArgument(args, "--client", "localhost:42070");

            Console.WriteLine("Starting Doyen C# Algorithm Script Manager...");
            Console.WriteLine($"gRPC server will listen on: {serverAddress}");
            Console.WriteLine($"gRPC client will connect to: {clientAddress}");

            var serverHost = serverAddress.Split(':')[0];
            var serverPort = int.Parse(serverAddress.Split(':')[1]);
            var clientHost = clientAddress.Split(':')[0];
            var clientPort = int.Parse(clientAddress.Split(':')[1]);

            // Create gRPC client to communicate with Doyen
            var channel = new Channel(clientHost, clientPort, ChannelCredentials.Insecure);
            var client = new AlgorithmServer.AlgorithmServerClient(channel);

            // Create the algorithm script manager
            var scriptManager = new AlgorithmScriptManager(client);

            // Start the gRPC server
            var grpcServer = new Server
            {
                Services = { AlgorithmServer.BindService(scriptManager) },
                Ports = { new ServerPort(serverHost, serverPort, ServerCredentials.Insecure) }
            };

            grpcServer.Start();
            Console.WriteLine($"gRPC server started on {serverAddress}");
            Console.WriteLine("Algorithm Script Manager started. Press Ctrl+C to stop.");

            var cts = new CancellationTokenSource();
            Console.CancelKeyPress += (_, e) =>
            {
                e.Cancel = true;
                cts.Cancel();
            };

            // Start the message processing loop
            var messageProcessingTask = StartMessageProcessingLoopAsync(cts.Token);

            // Wait for cancellation
            try
            {
                await Task.Delay(Timeout.Infinite, cts.Token);
            }
            catch (OperationCanceledException)
            {
                Console.WriteLine("Shutting down...");
            }

            // Shutdown server and client
            await grpcServer.ShutdownAsync();
            await channel.ShutdownAsync();
            Console.WriteLine("Algorithm Script Manager stopped.");
        }

        private static async Task StartMessageProcessingLoopAsync(CancellationToken token)
        {
            Console.WriteLine("Starting message processing loop...");
            try
            {
                while (!token.IsCancellationRequested)
                {
                    try
                    {
                        // Process any pending tasks or messages
                        await Task.Delay(100, token);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"Error in message processing loop: {ex.Message}");
                        await Task.Delay(1000, token);
                    }
                }
            }
            catch (OperationCanceledException)
            {
                Console.WriteLine("Message processing loop cancelled");
            }
        }

        private static string GetArgument(string[] args, string name, string defaultValue)
        {
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i].Equals(name, StringComparison.OrdinalIgnoreCase))
                {
                    return args[i + 1];
                }
            }
            return defaultValue;
        }
    }
}
